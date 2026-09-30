from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.policy import ToolPolicy
from appshak_substrate.tool_gateway import ToolGateway
from appshak_substrate.types import SubstrateEvent, iso_now


class TestDurableOwnerTask(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="appshak_wp3_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.worktree = self.root / "worker"
        self.worktree.mkdir()
        self.db = self.root / "mail.db"
        self.store = SQLiteMailStore(self.db, lease_seconds=0.3, poll_interval=0.01)
        self.workspace_id = ToolGateway.workspace_identity("command", self.worktree)
        self.gateway = ToolGateway(
            mail_store=self.store, policy=ToolPolicy(chief_agent_id="command",
                allowed_command_prefixes=[(sys.executable,)]),
            workspace_roots={"command": self.worktree}, command_timeout_seconds=3,
        )

    def task(self, name: str = "one", *, assign: bool = True) -> dict:
        task = self.store.create_owner_task(
            owner_id="owner", objective=f"Write {name} evidence", authority_id=f"authority:{name}",
            source_request_id=f"owner-request:{name}",
        )
        if assign:
            task = self.store.assign_owner_task(
                task_id=task["task_id"], agent_id="command", workspace_id=self.workspace_id,
                authority_id=f"authority:{name}", actor_id="owner", source_ref=f"assignment:{name}",
            )
        return task

    def request(self, task: dict, name: str = "one", *, action: str = "WRITE_FILE",
                payload: dict | None = None) -> dict:
        return {
            "task_id": task["task_id"], "agent_id": "command", "authorized_by": "command",
            "action_type": action, "working_dir": str(self.worktree),
            "authority_id": task["authority_id"], "source_request_id": f"execution:{name}",
            "workspace_id": self.workspace_id, "requested_operation": action,
            "created_at": iso_now(), "reply_to": "command",
            "payload": payload or {"path": f"{name}.txt", "content": name,
                                   "idempotency_key": f"key:{name}"},
        }

    def reserve(self, request: dict) -> dict:
        normalized = self.gateway.policy.validate(self.gateway._coerce_request(request),
                                                   worktree_root=self.worktree).normalized_payload
        normalized.update({key: request[key] for key in
                           ("authority_id", "source_request_id", "workspace_id",
                            "requested_operation", "created_at")})
        normalized["worker_id"] = request["agent_id"]
        return self.store.reserve_attempt(
            source_request_id=request["source_request_id"], source_event_id=None,
            idempotency_key=request["payload"]["idempotency_key"],
            authority_id=request["authority_id"], agent_id=request["agent_id"],
            workspace_id=request["workspace_id"], requested_operation=request["requested_operation"],
            created_at=request["created_at"], task_id=request["task_id"],
            request={"working_dir": request["working_dir"], "payload": normalized,
                     "authorized_by": request["authorized_by"], "correlation_id": None,
                     "reply_to": request["reply_to"], "task_id": request["task_id"]},
        )

    def test_creation_persists_without_execution(self) -> None:
        task = self.task(assign=False)
        reopened = SQLiteMailStore(self.db)
        observed = reopened.get_owner_task(task["task_id"])
        self.assertEqual(observed["state"], "CREATED")
        self.assertEqual(observed["objective"], "Write one evidence")
        self.assertEqual(observed["attempts"], [])
        self.assertEqual(observed["history"][0]["event_type"], "task_created")

    def test_duplicate_creation_is_idempotent_and_conflicts_fail(self) -> None:
        first = self.task(assign=False)
        same = self.store.create_owner_task(owner_id="owner", objective="Write one evidence",
                                            authority_id="authority:one", source_request_id="owner-request:one")
        self.assertEqual(first["task_id"], same["task_id"])
        self.assertEqual(len(self.store.get_owner_task(first["task_id"])["history"]), 1)
        with self.assertRaisesRegex(ValueError, "different owner-task"):
            self.store.create_owner_task(owner_id="owner", objective="Different",
                                         authority_id="authority:one", source_request_id="owner-request:one")

    def test_assignment_persists_and_duplicate_assignment_is_idempotent(self) -> None:
        task = self.task()
        same = self.store.assign_owner_task(task_id=task["task_id"], agent_id="command",
            workspace_id=self.workspace_id, authority_id="authority:one", actor_id="owner",
            source_ref="assignment:one")
        self.assertEqual(same["state"], "ASSIGNED")
        observed = SQLiteMailStore(self.db).get_owner_task(task["task_id"])
        self.assertEqual(observed["assigned_agent"], "command")
        self.assertEqual(observed["workspace_id"], self.workspace_id)
        self.assertIsNotNone(observed["assigned_at"])
        self.assertEqual([e["event_type"] for e in observed["history"]],
                         ["task_created", "task_assigned"])

    def test_assignment_rejects_wrong_owner_or_authority(self) -> None:
        task = self.task(assign=False)
        for actor, authority in (("stranger", "authority:one"), ("owner", "authority:other")):
            with self.assertRaisesRegex(ValueError, "owner or authority"):
                self.store.assign_owner_task(task_id=task["task_id"], agent_id="command",
                    workspace_id=self.workspace_id, authority_id=authority, actor_id=actor,
                    source_ref="assignment:wrong")
        self.assertEqual(self.store.get_owner_task(task["task_id"])["state"], "CREATED")

    def test_execution_links_attempt_and_stops_at_ready_for_validation(self) -> None:
        task = self.task()
        result = self.gateway.execute(self.request(task))
        self.assertTrue(result.allowed, result.reason)
        observed = self.store.get_owner_task(task["task_id"])
        self.assertEqual(observed["state"], "READY_FOR_VALIDATION")
        self.assertNotEqual(observed["state"], "COMPLETE")
        self.assertEqual(observed["attempts"][0]["attempt_id"], result.attempt_id)
        self.assertEqual(observed["attempts"][0]["task_id"], task["task_id"])
        self.assertEqual(observed["artifacts"][0]["reference"], str(self.worktree / "one.txt"))
        self.assertEqual([e["event_type"] for e in observed["history"]][-2:],
                         ["task_execution_started", "task_execution_succeeded"])

    def test_failure_is_distinct_and_does_not_retry(self) -> None:
        task = self.task()
        script = self.worktree / "fail.py"
        script.write_text("import sys\nsys.exit(7)\n", encoding="utf-8")
        request = self.request(task, action="RUN_CMD", payload={
            "argv": [sys.executable, str(script)], "idempotency_key": "key:failure"})
        result = self.gateway.execute(request)
        self.assertFalse(result.allowed)
        observed = self.store.get_owner_task(task["task_id"])
        self.assertEqual(observed["state"], "EXECUTION_FAILED")
        self.assertEqual(observed["attempts"][0]["state"], "FAILED")
        self.assertEqual(len(self.store.list_attempts()), 1)
        self.assertEqual(observed["history"][-1]["event_type"], "task_execution_failed")
        self.assertFalse(self.gateway.execute(self.request(task, "another")).allowed)
        self.assertEqual(len(self.store.list_attempts()), 1)

    def test_unknown_blocks_replay_and_new_attempts(self) -> None:
        task = self.task()
        request = self.request(task)
        attempt = self.reserve(request)
        generation = self.store.begin_attempt(attempt["attempt_id"], "worker:one", 1)
        self.assertEqual(generation, 1)
        self.assertIsNotNone(self.store.record_attempt_outcome(attempt["attempt_id"], "worker:one",
            generation, "NEEDS_RECONCILIATION", {"allowed": False, "reason": "unknown"}))
        observed = self.store.get_owner_task(task["task_id"])
        self.assertEqual(observed["state"], "NEEDS_RECONCILIATION")
        self.assertEqual(observed["attempts"][0]["state"], "NEEDS_RECONCILIATION")
        self.assertEqual(observed["history"][-1]["event_type"], "task_needs_reconciliation")
        self.assertFalse(self.gateway.execute(request).allowed)
        self.assertFalse(self.gateway.execute(self.request(task, "another")).allowed)
        self.assertEqual(len(self.store.list_attempts()), 1)

    def test_stale_fence_cannot_advance_task(self) -> None:
        task = self.task()
        attempt = self.reserve(self.request(task))
        generation = self.store.begin_attempt(attempt["attempt_id"], "worker:one", 0.1)
        time.sleep(0.13)
        self.assertEqual(self.store.reconcile_attempts()["fenced_unknown"], 1)
        self.assertIsNone(self.store.record_attempt_outcome(attempt["attempt_id"], "worker:one",
            generation, "SUCCEEDED", {"allowed": True}))
        self.assertEqual(self.store.get_owner_task(task["task_id"])["state"], "NEEDS_RECONCILIATION")

    def test_authority_and_assignment_continuity(self) -> None:
        task = self.task()
        bad = self.request(task, "bad")
        bad["authority_id"] = "authority:wrong"
        self.assertFalse(self.gateway.execute(bad).allowed)
        bad = self.request(task, "bad-worker")
        bad["workspace_id"] = "wrong"
        self.assertFalse(self.gateway.execute(bad).allowed)
        good = self.request(task)
        self.assertTrue(self.gateway.execute(good).allowed)
        attempt = self.store.get_owner_task(task["task_id"])["attempts"][0]
        for field in ("authority_id", "source_request_id", "agent_id", "workspace_id",
                      "requested_operation", "task_id"):
            self.assertEqual(attempt[field], good[field])
        self.assertEqual(len(self.store.list_attempts()), 1)

    def test_restart_reconciles_executing_against_attempt_truth(self) -> None:
        task = self.task()
        attempt = self.reserve(self.request(task))
        self.store.begin_attempt(attempt["attempt_id"], "worker:one", 0.1)
        self.assertEqual(SQLiteMailStore(self.db).get_owner_task(task["task_id"])["state"], "EXECUTING")
        time.sleep(0.13)
        restarted = SQLiteMailStore(self.db)
        restarted.reconcile_attempts()
        observed = restarted.get_owner_task(task["task_id"])
        self.assertEqual(observed["state"], "NEEDS_RECONCILIATION")
        self.assertEqual(observed["attempts"][0]["state"], "NEEDS_RECONCILIATION")

    def test_one_task_can_link_multiple_attempts_without_early_ready(self) -> None:
        task = self.task()
        first = self.reserve(self.request(task, "first"))
        second = self.reserve(self.request(task, "second"))
        first_generation = self.store.begin_attempt(first["attempt_id"], "worker:one", 1)
        self.store.record_attempt_outcome(first["attempt_id"], "worker:one", first_generation,
                                          "SUCCEEDED", {"allowed": True})
        self.assertEqual(self.store.get_owner_task(task["task_id"])["state"], "EXECUTING")
        second_generation = self.store.begin_attempt(second["attempt_id"], "worker:two", 1)
        self.store.record_attempt_outcome(second["attempt_id"], "worker:two", second_generation,
                                          "SUCCEEDED", {"allowed": True})
        observed = self.store.get_owner_task(task["task_id"])
        self.assertEqual(observed["state"], "READY_FOR_VALIDATION")
        self.assertEqual(len(observed["attempts"]), 2)

    def test_legacy_wp2_attempt_table_migrates_without_losing_row(self) -> None:
        legacy = self.root / "legacy.db"
        with closing(sqlite3.connect(legacy)) as conn:
            conn.execute("""CREATE TABLE execution_attempts (
                attempt_id TEXT PRIMARY KEY, source_request_id TEXT NOT NULL UNIQUE,
                source_event_id INTEGER, idempotency_key TEXT NOT NULL UNIQUE,
                authority_id TEXT NOT NULL, agent_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
                requested_operation TEXT NOT NULL, created_at TEXT NOT NULL, request_json TEXT NOT NULL,
                state TEXT NOT NULL, generation INTEGER NOT NULL DEFAULT 0, owner_id TEXT,
                lease_expiry TEXT, started_at TEXT, outcome_json TEXT, audit_id INTEGER,
                published_event_id INTEGER, acknowledged_at TEXT, updated_at TEXT NOT NULL)""")
            conn.execute("""INSERT INTO execution_attempts
                (attempt_id, source_request_id, idempotency_key, authority_id, agent_id,
                 workspace_id, requested_operation, created_at, request_json, state, updated_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("legacy-attempt", "legacy-request", "legacy-key", "authority:legacy", "command",
                 self.workspace_id, "READ_FILE", iso_now(), "{}", "RESERVED", iso_now()))
            conn.commit()
        migrated = SQLiteMailStore(legacy)
        self.assertIsNone(migrated.get_attempt("legacy-attempt")["task_id"])
        self.assertIsNotNone(migrated.create_owner_task(owner_id="owner", objective="new work",
            authority_id="authority:new", source_request_id="new-request"))
        self.assertIsNone(SQLiteMailStore(legacy).get_attempt("legacy-attempt")["task_id"])

    def test_cli_creates_and_inspects_without_dispatch(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        base = [sys.executable, "-m", "appshak_substrate.owner_task_cli", "--db-path", str(self.db)]
        created = subprocess.run(base + ["create", "--owner-id", "owner", "--objective", "CLI work",
            "--authority-id", "authority:cli", "--source-request-id", "owner-request:cli"],
            cwd=repo, text=True, capture_output=True, check=True)
        task = json.loads(created.stdout)
        self.assertEqual(task["state"], "CREATED")
        inspected = subprocess.run(base + ["inspect", "--task-id", task["task_id"]],
            cwd=repo, text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(inspected.stdout)["attempts"], [])

    def test_golden_owner_worker_restart(self) -> None:
        task = self.task()
        request = self.request(task, "golden", payload={
            "path": "golden.txt", "content": "exact golden content", "idempotency_key": "key:golden"})
        event_id = self.store.append_event(SubstrateEvent(type="TOOL_REQUEST", origin_id="command",
            target_agent="command", payload={"request": request, "reply_to": "command"}))
        worker = subprocess.Popen([sys.executable, "-m", "appshak_substrate.worker_process",
            "--db-path", str(self.db), "--agent-id", "command", "--worktree", str(self.worktree),
            "--consumer-id", "wp3-golden", "--log-path", str(self.root / "worker.log"),
            "--lease-seconds", "0.3", "--heartbeat-interval-seconds", "0.05"],
            cwd=str(Path(__file__).resolve().parents[1]), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline and self.store.get_event(event_id).status != "DONE":
                if worker.poll() is not None:
                    self.fail(f"worker exited: {worker.communicate()[1]}")
                time.sleep(0.05)
            self.assertEqual(self.store.get_event(event_id).status, "DONE")
        finally:
            worker.terminate()
            try:
                worker.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.communicate(timeout=3)
        self.assertEqual((self.worktree / "golden.txt").read_text(encoding="utf-8"),
                         "exact golden content")
        observed = SQLiteMailStore(self.db).get_owner_task(task["task_id"])
        self.assertEqual(observed["state"], "READY_FOR_VALIDATION")
        self.assertEqual(observed["assigned_agent"], "command")
        self.assertEqual(observed["attempts"][0]["state"], "SUCCEEDED")
        self.assertEqual(observed["attempts"][0]["task_id"], task["task_id"])
        self.assertIsNotNone(observed["attempts"][0]["published_event_id"])
        self.assertIsNotNone(observed["attempts"][0]["acknowledged_at"])
        self.assertEqual(observed["artifacts"][0]["reference"], str(self.worktree / "golden.txt"))


if __name__ == "__main__":
    unittest.main()
