"""S2D proof through a separate worker process and a constrained loopback API."""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from appshak_projection.office_state import read_office_state
from appshak_substrate.artifact_validator import ArtifactValidator
from appshak_substrate.baton_routing import CapabilityRoutingPolicy, RouteTarget, VerifiedBatonManager
from appshak_substrate.external_handoff import ExternalHandoffManager
from appshak_substrate.external_handoff_http import create_handoff_server
from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.policy import ToolPolicy
from appshak_substrate.tool_gateway import ToolGateway
from appshak_substrate.types import iso_now


class TestExternalHandoff(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="appshak_s2d_")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.repo = root / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "s2d@example.invalid"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "S2D Test"], cwd=self.repo, check=True)
        (self.repo / "evidence.md").write_text("source evidence\n", encoding="utf-8")
        subprocess.run(["git", "add", "evidence.md"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=self.repo, check=True)
        self.head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()
        self.source_root = root / "source"
        self.target_root = root / "external"
        self.source_root.mkdir()
        self.target_root.mkdir()
        self.db = root / "mail.db"
        self.store = SQLiteMailStore(self.db)
        self.gateway = ToolGateway(mail_store=self.store, policy=ToolPolicy(chief_agent_id="command"),
                                   workspace_roots={"command": self.source_root, "external-worker": self.target_root})
        self.validator = ArtifactValidator(mail_store=self.store, tool_gateway=self.gateway)
        self.batons = VerifiedBatonManager(self.store, self.repo)
        self.handoffs = ExternalHandoffManager(self.store)
        self.secret = secrets.token_urlsafe(32)

    def test_existing_dispatch_schema_migrates_in_place(self) -> None:
        old_db = Path(self.temp.name) / "old-dispatch.db"
        with closing(sqlite3.connect(old_db)) as conn:
            conn.execute("""CREATE TABLE baton_dispatches (dispatch_id TEXT PRIMARY KEY,
                baton_id TEXT NOT NULL UNIQUE, required_capability TEXT NOT NULL,
                status TEXT NOT NULL, target_id TEXT, route_json TEXT, context_json TEXT NOT NULL,
                reason TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
            conn.commit()
        SQLiteMailStore(old_db)
        with closing(sqlite3.connect(old_db)) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(baton_dispatches)")}
            values = ("first", "BATON-A", "INTEGRATION", "READY_FOR_EXTERNAL_DISPATCH", "{}",
                      "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", "same-digest")
            conn.execute("""INSERT INTO baton_dispatches
                (dispatch_id, baton_id, required_capability, status, context_json,
                 created_at, updated_at, credential_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", values)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("""INSERT INTO baton_dispatches
                    (dispatch_id, baton_id, required_capability, status, context_json,
                     created_at, updated_at, credential_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    ("second", "BATON-B", *values[2:]))
        self.assertTrue({"handoff_task_id", "attempt_id", "credential_sha256", "chief_authorized_by", "pickup_generation",
                         "result_reference", "result_sha256"} <= columns)

    def _source_baton(self) -> dict:
        task = self.store.create_owner_task(owner_id="owner", objective="Produce source evidence",
                                            authority_id="authority:source", source_request_id="owner:source")
        self.store.add_acceptance_criterion(task_id=task["task_id"], criterion_type="EXACT_TEXT",
            config={"expected": "done"}, created_by="owner", source_ref="source:criterion")
        identity = ToolGateway.workspace_identity("command", self.source_root)
        self.store.assign_owner_task(task_id=task["task_id"], agent_id="command", workspace_id=identity,
                                     authority_id=task["authority_id"], actor_id="owner", source_ref="source:assignment")
        result = self.gateway.execute({"task_id": task["task_id"], "agent_id": "command",
            "authorized_by": "command", "action_type": "WRITE_FILE", "working_dir": str(self.source_root),
            "authority_id": task["authority_id"], "source_request_id": "source:write", "workspace_id": identity,
            "requested_operation": "WRITE_FILE", "created_at": iso_now(),
            "payload": {"path": "source.txt", "content": "done", "idempotency_key": "source:write"}})
        self.assertTrue(result.allowed, result.reason)
        artifact = self.store.get_owner_task(task["task_id"])["artifacts"][0]
        validation = self.validator.validate(task_id=task["task_id"], artifact_id=artifact["artifact_id"],
                                             source_request_id="source:validation")
        self.assertEqual(validation["status"], "PASSED")
        baton = self.batons.create_baton(baton_id="BATON-S2D-TEST", source_baton_id=None,
            task_id=task["task_id"], work_package="S2D fixture", next_objective="Produce external evidence",
            git_commit=self.head, completion_status="COMPLETE", current_state={"task_state": "COMPLETE"},
            results={"tests": "PASS"}, evidence_references=["evidence.md"],
            validation_id=validation["validation_id"], required_capability="INTEGRATION", producer_id="test:s2d")
        self.assertEqual(self.batons.verify_baton(baton["baton_id"])["status"], "VERIFIED")
        return baton

    def _policy(self, *, enabled: bool = True) -> CapabilityRoutingPolicy:
        return CapabilityRoutingPolicy((RouteTarget("external-worker", ("INTEGRATION",),
            "configurable-provider-class", "configurable-model-class", enabled=enabled,
            workspace_root=str(self.target_root)),), version="s2d-test-policy")

    def _ready(self) -> tuple[dict, dict, CapabilityRoutingPolicy]:
        baton = self._source_baton()
        policy = self._policy()
        dispatch = self.batons.dispatch(baton["baton_id"], policy)
        task = self.store.create_owner_task(owner_id="owner", objective=baton["next_objective"],
            authority_id="authority:external", source_request_id=f"handoff:{dispatch['dispatch_id']}")
        self.store.add_acceptance_criterion(task_id=task["task_id"], criterion_type="EXACT_TEXT",
            config={"expected": "accepted"}, created_by="owner", source_ref="external:criterion")
        self.store.assign_owner_task(task_id=task["task_id"], agent_id="external-worker",
            workspace_id=ToolGateway.workspace_identity("external-worker", self.target_root),
            authority_id=task["authority_id"], actor_id="owner", source_ref="external:assignment")
        self.handoffs.prepare(dispatch_id=dispatch["dispatch_id"], task_id=task["task_id"],
                              worker_secret=self.secret, authorized_by="command")
        return dispatch, task, policy

    def _serve(self):
        server = create_handoff_server(self.handoffs)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}"

    def _worker(self, endpoint: str, dispatch_id: str, content: str = "accepted", *extra: str):
        env = os.environ.copy()
        env["APPSHAK_HANDOFF_SECRET"] = self.secret
        return subprocess.run([sys.executable, "-m", "appshak_substrate.external_worker_demo",
            "--endpoint", endpoint, "--dispatch-id", dispatch_id, "--target-id", "external-worker",
            "--worker-id", "worker-1", "--content", content, *extra],
            cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, check=True)

    def test_no_target_waits_without_task_or_attempt(self) -> None:
        baton = self._source_baton()
        dispatch = self.batons.dispatch(baton["baton_id"], CapabilityRoutingPolicy.default())
        self.assertEqual(dispatch["status"], "WAITING_FOR_CAPABILITY")
        self.assertEqual(dispatch["reason"], "no eligible configured target")
        self.assertIsNone(dispatch["target_id"])
        self.assertIsNone(dispatch["attempt_id"])
        self.assertEqual(VerifiedBatonManager(SQLiteMailStore(self.db), self.repo)
                         .get_baton(baton["baton_id"])["dispatch"]["status"], "WAITING_FOR_CAPABILITY")

    def test_golden_separate_process_validation_gate_and_projection(self) -> None:
        dispatch, task, policy = self._ready()
        handoff = self.handoffs.publish(dispatch["dispatch_id"], policy)
        self.assertEqual(handoff["status"], "HANDOFF_DISPATCHED")
        self.assertEqual(handoff["route"]["capability"], "INTEGRATION")
        self.assertEqual(handoff["route"]["provider_class"], "configurable-provider-class")
        self.assertEqual(handoff["route"]["model_class"], "configurable-model-class")
        self.assertEqual(handoff["handoff_task_id"], task["task_id"])
        self.assertNotIn("credential_sha256", handoff)
        output = self._worker(self._serve(), dispatch["dispatch_id"])
        self.assertIn("RESULT_RETURNED", output.stdout)
        durable = ExternalHandoffManager(SQLiteMailStore(self.db)).get(dispatch["dispatch_id"])
        self.assertEqual(durable["status"], "RESULT_RETURNED")
        self.assertEqual(self.store.get_owner_task(task["task_id"])["state"], "READY_FOR_VALIDATION")
        projected = read_office_state(self.db)
        self.assertEqual(next(b for b in projected["batons"] if b["baton_id"] == dispatch["baton_id"])
                         ["dispatch_status"], "RESULT_RETURNED")
        self.assertEqual(read_office_state(self.db), projected)
        artifact = self.store.get_owner_task(task["task_id"])["artifacts"][0]
        self.assertEqual(artifact["attempt_id"], durable["attempt_id"])
        validation = self.validator.validate(task_id=task["task_id"], artifact_id=artifact["artifact_id"],
                                             source_request_id="external:validation")
        self.assertEqual(validation["status"], "PASSED")
        self.assertEqual(self.store.get_owner_task(task["task_id"])["state"], "COMPLETE")
        self.assertEqual(self.handoffs.publish(dispatch["dispatch_id"], policy)["attempt_id"], durable["attempt_id"])
        self.assertEqual(self.handoffs.submit_result(dispatch["dispatch_id"], target_id="external-worker",
            worker_id="worker-1", secret=self.secret, generation=durable["pickup_generation"],
            state="SUCCEEDED", sha256=durable["result_sha256"])["status"], "RESULT_RETURNED")

    def test_negative_validation_does_not_complete(self) -> None:
        dispatch, task, policy = self._ready()
        self.handoffs.publish(dispatch["dispatch_id"], policy)
        self._worker(self._serve(), dispatch["dispatch_id"], "rejected")
        artifact = self.store.get_owner_task(task["task_id"])["artifacts"][0]
        validation = self.validator.validate(task_id=task["task_id"], artifact_id=artifact["artifact_id"],
                                             source_request_id="external:validation-fail")
        self.assertEqual(validation["status"], "FAILED")
        self.assertNotEqual(self.store.get_owner_task(task["task_id"])["state"], "COMPLETE")

    def test_restart_and_duplicate_pickup_are_fenced(self) -> None:
        dispatch, task, policy = self._ready()
        first = self.handoffs.publish(dispatch["dispatch_id"], policy)
        self.assertEqual(self.handoffs.publish(dispatch["dispatch_id"], policy)["attempt_id"], first["attempt_id"])
        self._worker(self._serve(), dispatch["dispatch_id"], "accepted", "--stop-after-pickup")
        reopened = ExternalHandoffManager(SQLiteMailStore(self.db))
        self.assertEqual(reopened.reconcile(dispatch["dispatch_id"])["status"], "EXTERNAL_PICKUP_ACKNOWLEDGED")
        picked = reopened.pickup(dispatch["dispatch_id"], target_id="external-worker", worker_id="worker-1",
                                secret=self.secret)
        self.assertEqual(picked["pickup_generation"], 1)
        with self.assertRaises(ValueError):
            reopened.pickup(dispatch["dispatch_id"], target_id="external-worker", worker_id="worker-2",
                            secret=self.secret)
        self.assertEqual(self.store.get_owner_task(task["task_id"])["state"], "EXECUTING")

    def test_invalid_identity_and_digest_rejected(self) -> None:
        dispatch, task, policy = self._ready()
        self.handoffs.publish(dispatch["dispatch_id"], policy)
        with self.assertRaises(PermissionError):
            self.handoffs.pickup(dispatch["dispatch_id"], target_id="wrong", worker_id="worker-1",
                                 secret=self.secret)
        picked = self.handoffs.pickup(dispatch["dispatch_id"], target_id="external-worker",
                                      worker_id="worker-1", secret=self.secret)
        Path(picked["result_reference"]).write_text("accepted", encoding="utf-8")
        for wrong in ("wrong-handoff",):
            with self.assertRaises(ValueError):
                self.handoffs.submit_result(wrong, target_id="external-worker", worker_id="worker-1",
                    secret=self.secret, generation=1, state="SUCCEEDED", sha256=hashlib.sha256(b"accepted").hexdigest())
        with self.assertRaises(ValueError):
            self.handoffs.submit_result(dispatch["dispatch_id"], target_id="external-worker",
                worker_id="worker-1", secret=self.secret, generation=1, state="SUCCEEDED", sha256="0" * 64)
        self.assertEqual(self.handoffs.get(dispatch["dispatch_id"])["status"], "EXTERNAL_PICKUP_ACKNOWLEDGED")
        self.assertNotEqual(self.store.get_owner_task(task["task_id"])["state"], "COMPLETE")

    def test_target_unavailable_after_route_and_expired_effect_unknown(self) -> None:
        dispatch, task, policy = self._ready()
        self.assertEqual(self.handoffs.publish(dispatch["dispatch_id"], self._policy(enabled=False))["status"],
                         "WAITING_FOR_CAPABILITY")
        self.assertIsNone(self.handoffs.get(dispatch["dispatch_id"])["attempt_id"])
        # A fresh dispatch is needed after the target becomes available again.
        self.batons.dispatch(dispatch["baton_id"], policy)
        self.handoffs.publish(dispatch["dispatch_id"], policy)
        self.handoffs.pickup(dispatch["dispatch_id"], target_id="external-worker",
                             worker_id="worker-1", secret=self.secret, lease_seconds=0.1)
        time.sleep(0.2)
        self.assertEqual(self.handoffs.reconcile(dispatch["dispatch_id"])["status"], "UNKNOWN")
        self.assertEqual(self.store.get_owner_task(task["task_id"])["state"], "NEEDS_RECONCILIATION")
        with self.assertRaises(ValueError):
            self.handoffs.pickup(dispatch["dispatch_id"], target_id="external-worker",
                                 worker_id="worker-1", secret=self.secret)

    def test_pre_dispatch_restart_and_wrong_task_cannot_bind(self) -> None:
        baton = self._source_baton()
        policy = self._policy()
        dispatch = self.batons.dispatch(baton["baton_id"], policy)
        wrong = self.store.create_owner_task(owner_id="different-owner", objective=baton["next_objective"],
            authority_id="wrong:authority", source_request_id=f"handoff:{dispatch['dispatch_id']}")
        self.store.add_acceptance_criterion(task_id=wrong["task_id"], criterion_type="FILE_EXISTS",
            config={}, created_by="different-owner", source_ref="wrong:criterion")
        self.store.assign_owner_task(task_id=wrong["task_id"], agent_id="external-worker",
            workspace_id=ToolGateway.workspace_identity("external-worker", self.target_root),
            authority_id=wrong["authority_id"], actor_id="different-owner", source_ref="wrong:assignment")
        with self.assertRaises(ValueError):
            self.handoffs.prepare(dispatch_id=dispatch["dispatch_id"], task_id=wrong["task_id"],
                                  worker_secret=self.secret, authorized_by="command")
        self.assertEqual(self.handoffs.get(dispatch["dispatch_id"])["status"], "READY_FOR_EXTERNAL_DISPATCH")
        task = self.store.create_owner_task(owner_id="owner", objective=baton["next_objective"],
            authority_id="right:authority", source_request_id=f"handoff:{dispatch['dispatch_id']}:wrong")
        self.store.add_acceptance_criterion(task_id=task["task_id"], criterion_type="FILE_EXISTS",
            config={}, created_by="owner", source_ref="right:criterion")
        self.store.assign_owner_task(task_id=task["task_id"], agent_id="external-worker",
            workspace_id=ToolGateway.workspace_identity("external-worker", self.target_root),
            authority_id=task["authority_id"], actor_id="owner", source_ref="right:assignment")
        with self.assertRaises(ValueError):
            self.handoffs.prepare(dispatch_id=dispatch["dispatch_id"], task_id=task["task_id"],
                                  worker_secret=self.secret, authorized_by="command")
        reopened = ExternalHandoffManager(SQLiteMailStore(self.db))
        self.assertIsNone(reopened.get(dispatch["dispatch_id"])["handoff_task_id"])
        self.assertIsNone(reopened.get(dispatch["dispatch_id"])["attempt_id"])

    def test_external_failure_is_terminal_without_validation_or_completion(self) -> None:
        dispatch, task, policy = self._ready()
        self.handoffs.publish(dispatch["dispatch_id"], policy)
        result = self._worker(self._serve(), dispatch["dispatch_id"], "", "--fail")
        self.assertIn("FAILED", result.stdout)
        self.assertEqual(self.store.get_owner_task(task["task_id"])["state"], "EXECUTION_FAILED")
        self.assertEqual(self.store.get_owner_task(task["task_id"])["artifacts"], [])
        self.assertEqual(self.handoffs.get(dispatch["dispatch_id"])["status"], "FAILED")

    def test_crash_after_effect_without_result_does_not_repeat_side_effect(self) -> None:
        dispatch, task, policy = self._ready()
        self.handoffs.publish(dispatch["dispatch_id"], policy)
        endpoint = self._serve()
        result = self._worker(endpoint, dispatch["dispatch_id"], "accepted", "--stop-after-write")
        self.assertIn("EFFECT_UNCONFIRMED", result.stdout)
        result_path = Path(self.handoffs.get(dispatch["dispatch_id"])["result_reference"])
        self.assertEqual(result_path.read_text(encoding="utf-8"), "accepted")
        with self.assertRaises(ValueError):
            self.handoffs.pickup(dispatch["dispatch_id"], target_id="external-worker",
                                 worker_id="worker-2", secret=self.secret)
        # The same owner can return the exact evidence without writing it again.
        again = self._worker(endpoint, dispatch["dispatch_id"], "accepted")
        self.assertIn("RESULT_RETURNED", again.stdout)
        self.assertEqual(self.store.get_owner_task(task["task_id"])["state"], "READY_FOR_VALIDATION")

    def test_reconcile_terminal_attempt_after_ack_update_gap(self) -> None:
        dispatch, task, policy = self._ready()
        handoff = self.handoffs.publish(dispatch["dispatch_id"], policy)
        picked = self.handoffs.pickup(dispatch["dispatch_id"], target_id="external-worker",
                                      worker_id="worker-1", secret=self.secret)
        content = b"accepted"
        Path(picked["result_reference"]).write_bytes(content)
        self.store.record_attempt_outcome(handoff["attempt_id"], "external-worker:worker-1",
            picked["pickup_generation"], "SUCCEEDED", {"allowed": True, "state": "SUCCEEDED",
            "return_code": 0, "result_sha256": hashlib.sha256(content).hexdigest()})
        self.assertEqual(self.handoffs.get(dispatch["dispatch_id"])["status"], "EXTERNAL_PICKUP_ACKNOWLEDGED")
        reopened = ExternalHandoffManager(SQLiteMailStore(self.db))
        self.assertEqual(reopened.reconcile(dispatch["dispatch_id"])["status"], "RESULT_RETURNED")
        self.assertEqual(self.store.get_owner_task(task["task_id"])["state"], "READY_FOR_VALIDATION")

    def test_worker_boundary_rejects_unauthorized_and_operational_methods(self) -> None:
        dispatch, task, policy = self._ready()
        self.handoffs.publish(dispatch["dispatch_id"], policy)
        endpoint = self._serve()
        body = (f'{{"dispatch_id":"{dispatch["dispatch_id"]}",'
                '"target_id":"external-worker","worker_id":"worker-1"}').encode("utf-8")
        with self.assertRaises(HTTPError) as unauthorized:
            urlopen(Request(endpoint + "/pickup", data=body, headers={
                "Authorization": "Bearer invalid", "Content-Type": "application/json"}, method="POST"))
        self.assertEqual(unauthorized.exception.code, 403)
        with self.assertRaises(HTTPError) as forbidden_operation:
            urlopen(Request(endpoint + "/publish", data=body, headers={
                "Authorization": f"Bearer {self.secret}", "Content-Type": "application/json"}, method="POST"))
        self.assertEqual(forbidden_operation.exception.code, 404)
        self.assertEqual(self.handoffs.get(dispatch["dispatch_id"])["status"], "HANDOFF_DISPATCHED")
        self.assertEqual(self.store.get_owner_task(task["task_id"])["state"], "ASSIGNED")

    def test_superseded_source_cannot_publish_stale_handoff(self) -> None:
        dispatch, task, policy = self._ready()
        self.batons.supersede(dispatch["baton_id"])
        with self.assertRaises(ValueError):
            self.handoffs.publish(dispatch["dispatch_id"], policy)
        self.assertIsNone(self.handoffs.get(dispatch["dispatch_id"])["attempt_id"])
        self.assertEqual(self.store.get_owner_task(task["task_id"])["state"], "ASSIGNED")

    def test_chief_policy_authorization_is_required_before_external_write(self) -> None:
        dispatch, task, policy = self._ready()
        with self.assertRaises(PermissionError):
            self.handoffs.prepare(dispatch_id=dispatch["dispatch_id"], task_id=task["task_id"],
                                  worker_secret=self.secret, authorized_by="owner")
        self.assertEqual(self.handoffs.get(dispatch["dispatch_id"])["chief_authorized_by"], "command")
        self.assertEqual(self.handoffs.publish(dispatch["dispatch_id"], policy)["status"], "HANDOFF_DISPATCHED")
