from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from appshak_substrate.artifact_validator import ArtifactValidator
from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.policy import ToolPolicy
from appshak_substrate.tool_gateway import ToolGateway
from appshak_substrate.types import iso_now


class TestPersistedValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="appshak_wp4_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.worktree = self.root / "worker"
        self.worktree.mkdir()
        self.db = self.root / "mail.db"
        self.store = SQLiteMailStore(self.db, lease_seconds=0.3, poll_interval=0.01)
        self.workspace_id = ToolGateway.workspace_identity("command", self.worktree)
        self.gateway = ToolGateway(mail_store=self.store, policy=ToolPolicy(chief_agent_id="command"),
            workspace_roots={"command": self.worktree}, command_timeout_seconds=3)
        self.validator = ArtifactValidator(mail_store=self.store, tool_gateway=self.gateway)

    def create_task(self, name: str, expected: str, *, criterion_type: str = "EXACT_TEXT") -> dict:
        task = self.store.create_owner_task(owner_id="owner", objective=f"Produce {name}",
            authority_id=f"authority:{name}", source_request_id=f"owner:{name}")
        config = {"expected": expected}
        if criterion_type == "FILE_EXISTS":
            config = {"expected": True}
        self.store.add_acceptance_criterion(task_id=task["task_id"],
            criterion_type=criterion_type, config=config, created_by="owner",
            source_ref=f"acceptance:{name}")
        return self.store.assign_owner_task(task_id=task["task_id"], agent_id="command",
            workspace_id=self.workspace_id, authority_id=f"authority:{name}", actor_id="owner",
            source_ref=f"assignment:{name}")

    def produce(self, task: dict, name: str, content: str) -> tuple[dict, dict]:
        result = self.gateway.execute({
            "task_id": task["task_id"], "agent_id": "command", "authorized_by": "command",
            "action_type": "WRITE_FILE", "working_dir": str(self.worktree),
            "authority_id": task["authority_id"], "source_request_id": f"production:{name}",
            "workspace_id": self.workspace_id, "requested_operation": "WRITE_FILE",
            "created_at": iso_now(), "payload": {"path": f"{name}.txt", "content": content,
                                                       "idempotency_key": f"production-key:{name}"},
        })
        self.assertTrue(result.allowed, result.reason)
        observed = self.store.get_owner_task(task["task_id"])
        self.assertEqual(len(observed["artifacts"]), 1)
        return observed, observed["artifacts"][0]

    def read_request(self, task: dict, artifact: dict, validation: dict) -> dict:
        return {
            "task_id": task["task_id"], "validation_id": validation["validation_id"],
            "agent_id": "command", "authorized_by": "owner", "action_type": "READ_FILE",
            "working_dir": str(self.worktree), "authority_id": task["authority_id"],
            "source_request_id": f"{validation['source_request_id']}:read",
            "workspace_id": self.workspace_id, "requested_operation": "READ_FILE",
            "created_at": iso_now(), "payload": {"path": artifact["reference"],
                "idempotency_key": f"validation:{validation['validation_id']}:read"},
        }

    def test_artifact_reference_persists_with_integrity_and_lineage(self) -> None:
        task = self.create_task("artifact", "hello")
        observed, artifact = self.produce(task, "artifact", "hello")
        self.assertEqual(observed["state"], "READY_FOR_VALIDATION")
        self.assertEqual(artifact["task_id"], task["task_id"])
        self.assertEqual(artifact["attempt_id"], observed["attempts"][0]["attempt_id"])
        self.assertEqual(artifact["kind"], "FILE")
        self.assertEqual(artifact["producer_id"], "command")
        self.assertEqual(artifact["workspace_id"], self.workspace_id)
        self.assertEqual(artifact["size_bytes"], 5)
        self.assertEqual(artifact["sha256"], hashlib.sha256(b"hello").hexdigest())
        reopened = SQLiteMailStore(self.db).get_owner_task(task["task_id"])
        self.assertEqual(reopened["artifacts"][0]["artifact_id"], artifact["artifact_id"])

    def test_execution_success_and_artifact_existence_are_not_complete(self) -> None:
        task = self.create_task("ungated", "hello")
        observed, artifact = self.produce(task, "ungated", "hello")
        self.assertTrue(Path(artifact["reference"]).exists())
        self.assertEqual(observed["attempts"][0]["state"], "SUCCEEDED")
        self.assertEqual(observed["state"], "READY_FOR_VALIDATION")
        self.assertEqual(observed["validations"], [])

    def test_validation_pass_persists_evidence_and_completes(self) -> None:
        task = self.create_task("pass", "hello")
        _, artifact = self.produce(task, "pass", "hello")
        validation = self.validator.validate(task_id=task["task_id"],
            artifact_id=artifact["artifact_id"], source_request_id="validation:pass")
        self.assertEqual(validation["status"], "PASSED")
        self.assertTrue(validation["evidence"]["integrity_match"])
        self.assertEqual(validation["checks"][0]["status"], "PASSED")
        self.assertEqual(self.store.get_owner_task(task["task_id"])["state"], "COMPLETE")

    def test_validation_failure_is_independent_and_not_complete(self) -> None:
        task = self.create_task("fail", "expected")
        _, artifact = self.produce(task, "fail", "producer claimed success")
        validation = self.validator.validate(task_id=task["task_id"],
            artifact_id=artifact["artifact_id"], source_request_id="validation:fail")
        self.assertEqual(validation["status"], "FAILED")
        self.assertEqual(validation["checks"][0]["status"], "FAILED")
        self.assertEqual(self.store.get_owner_task(task["task_id"])["state"], "VALIDATION_FAILED")

    def test_validation_error_is_distinct_from_failed_and_passed(self) -> None:
        task = self.create_task("error", "hello")
        _, artifact = self.produce(task, "error", "hello")
        Path(artifact["reference"]).unlink()
        validation = self.validator.validate(task_id=task["task_id"],
            artifact_id=artifact["artifact_id"], source_request_id="validation:error")
        self.assertEqual(validation["status"], "ERROR")
        self.assertEqual(self.store.get_owner_task(task["task_id"])["state"], "VALIDATION_ERROR")
        self.assertNotEqual(validation["status"], "FAILED")

    def test_artifact_mutation_before_completion_invalidates_pass(self) -> None:
        task = self.create_task("stale", "hello")
        _, artifact = self.produce(task, "stale", "hello")
        run = self.store.create_validation_run(task_id=task["task_id"], artifact_id=artifact["artifact_id"],
            validator_id="system:deterministic-file-validator", source_request_id="validation:stale")
        result = self.gateway.execute(self.read_request(task, artifact, run))
        self.assertTrue(result.allowed)
        Path(artifact["reference"]).write_text("mutated", encoding="utf-8")
        validation = self.store.complete_validation(run["validation_id"],
            observed_text=result.stdout, actor_id="system:deterministic-file-validator")
        self.assertEqual(validation["status"], "FAILED")
        self.assertFalse(validation["evidence"]["integrity_match"])
        self.assertNotEqual(self.store.get_owner_task(task["task_id"])["state"], "COMPLETE")

    def test_pass_and_completion_survive_restart(self) -> None:
        task = self.create_task("restart-pass", "durable")
        _, artifact = self.produce(task, "restart-pass", "durable")
        validation = self.validator.validate(task_id=task["task_id"],
            artifact_id=artifact["artifact_id"], source_request_id="validation:restart-pass")
        reopened = SQLiteMailStore(self.db).get_owner_task(task["task_id"])
        self.assertEqual(reopened["state"], "COMPLETE")
        self.assertEqual(reopened["validations"][0]["validation_id"], validation["validation_id"])
        self.assertEqual(reopened["validations"][0]["validated_sha256"], artifact["sha256"])
        self.assertEqual(Path(artifact["reference"]).read_bytes(), b"durable")

    def test_running_validation_reconciles_without_replay(self) -> None:
        task = self.create_task("running", "hello")
        _, artifact = self.produce(task, "running", "hello")
        run = self.store.create_validation_run(task_id=task["task_id"], artifact_id=artifact["artifact_id"],
            validator_id="system:deterministic-file-validator", source_request_id="validation:running")
        request = self.read_request(task, artifact, run)
        req = self.gateway._coerce_request(request)
        normalized = self.gateway.policy.validate(req, worktree_root=self.worktree).normalized_payload
        normalized.update({"authority_id": request["authority_id"], "worker_id": request["agent_id"],
            "source_request_id": request["source_request_id"], "workspace_id": request["workspace_id"],
            "requested_operation": request["requested_operation"], "created_at": request["created_at"]})
        attempt = self.store.reserve_attempt(source_request_id=request["source_request_id"],
            source_event_id=None, idempotency_key=request["payload"]["idempotency_key"],
            authority_id=request["authority_id"], agent_id=request["agent_id"],
            workspace_id=request["workspace_id"], requested_operation="READ_FILE",
            created_at=request["created_at"], task_id=task["task_id"], validation_id=run["validation_id"],
            request={"working_dir": request["working_dir"], "payload": normalized,
                     "authorized_by": "owner", "correlation_id": None,
                     "task_id": task["task_id"], "validation_id": run["validation_id"]})
        self.store.begin_attempt(attempt["attempt_id"], "validator:worker", 0.1)
        time.sleep(0.13)
        restarted = SQLiteMailStore(self.db)
        result = restarted.reconcile_attempts()
        self.assertEqual(result["fenced_unknown"], 1)
        self.assertEqual(restarted.get_validation_run(run["validation_id"])["status"],
                         "NEEDS_RECONCILIATION")
        self.assertEqual(len(restarted.list_attempts()), 2)

    def test_validation_attempt_preserves_wp1_authority(self) -> None:
        task = self.create_task("authority", "hello")
        _, artifact = self.produce(task, "authority", "hello")
        validation = self.validator.validate(task_id=task["task_id"],
            artifact_id=artifact["artifact_id"], source_request_id="validation:authority")
        attempt = next(item for item in self.store.get_owner_task(task["task_id"])["attempts"]
                       if item["validation_id"] == validation["validation_id"])
        self.assertEqual(attempt["authority_id"], task["authority_id"])
        self.assertEqual(attempt["workspace_id"], self.workspace_id)
        self.assertEqual(attempt["agent_id"], "command")
        self.assertEqual(attempt["requested_operation"], "READ_FILE")

    def test_failed_validation_does_not_auto_repair_or_retry(self) -> None:
        task = self.create_task("no-retry", "right")
        _, artifact = self.produce(task, "no-retry", "wrong")
        first = self.validator.validate(task_id=task["task_id"], artifact_id=artifact["artifact_id"],
            source_request_id="validation:no-retry")
        attempt_count = len(self.store.list_attempts())
        second = self.validator.validate(task_id=task["task_id"], artifact_id=artifact["artifact_id"],
            source_request_id="validation:no-retry")
        self.assertEqual(first["validation_id"], second["validation_id"])
        self.assertEqual(len(self.store.list_attempts()), attempt_count)
        self.assertEqual(self.store.get_owner_task(task["task_id"])["state"], "VALIDATION_FAILED")

    def test_unknown_production_attempt_cannot_validate(self) -> None:
        task = self.create_task("unknown", "hello")
        request = {"task_id": task["task_id"], "agent_id": "command", "authorized_by": "command",
            "action_type": "WRITE_FILE", "working_dir": str(self.worktree),
            "authority_id": task["authority_id"], "source_request_id": "production:unknown",
            "workspace_id": self.workspace_id, "requested_operation": "WRITE_FILE",
            "created_at": iso_now(), "payload": {"path": "unknown.txt", "content": "hello",
                                                       "idempotency_key": "production-key:unknown"}}
        req = self.gateway._coerce_request(request)
        normalized = self.gateway.policy.validate(req, worktree_root=self.worktree).normalized_payload
        normalized.update({"authority_id": task["authority_id"], "worker_id": "command",
            "source_request_id": request["source_request_id"], "workspace_id": self.workspace_id,
            "requested_operation": "WRITE_FILE", "created_at": request["created_at"]})
        attempt = self.store.reserve_attempt(source_request_id=request["source_request_id"], source_event_id=None,
            idempotency_key="production-key:unknown", authority_id=task["authority_id"], agent_id="command",
            workspace_id=self.workspace_id, requested_operation="WRITE_FILE", created_at=request["created_at"],
            task_id=task["task_id"], request={"working_dir": str(self.worktree), "payload": normalized,
                "authorized_by": "command", "correlation_id": None, "task_id": task["task_id"]})
        generation = self.store.begin_attempt(attempt["attempt_id"], "worker", 1)
        self.store.record_attempt_outcome(attempt["attempt_id"], "worker", generation,
            "NEEDS_RECONCILIATION", {"allowed": False, "reason": "unknown"})
        self.assertEqual(self.store.get_owner_task(task["task_id"])["state"], "NEEDS_RECONCILIATION")
        with self.assertRaisesRegex(ValueError, "not ready"):
            self.store.create_validation_run(task_id=task["task_id"], artifact_id="none",
                validator_id="validator", source_request_id="validation:unknown")

    def test_golden_pass_workflow_links_every_record(self) -> None:
        task = self.create_task("golden-pass", "golden")
        ready, artifact = self.produce(task, "golden-pass", "golden")
        validation = self.validator.validate(task_id=task["task_id"],
            artifact_id=artifact["artifact_id"], source_request_id="validation:golden-pass")
        reopened = SQLiteMailStore(self.db).get_owner_task(task["task_id"])
        self.assertEqual(ready["state"], "READY_FOR_VALIDATION")
        self.assertEqual(reopened["state"], "COMPLETE")
        self.assertEqual(validation["artifact_id"], artifact["artifact_id"])
        self.assertEqual(validation["related_attempt_id"], reopened["attempts"][1]["attempt_id"])
        self.assertEqual(reopened["validations"][0]["status"], "PASSED")

    def test_golden_fail_workflow_persists_failure(self) -> None:
        task = self.create_task("golden-fail", "A")
        _, artifact = self.produce(task, "golden-fail", "B")
        self.validator.validate(task_id=task["task_id"], artifact_id=artifact["artifact_id"],
            source_request_id="validation:golden-fail")
        reopened = SQLiteMailStore(self.db).get_owner_task(task["task_id"])
        self.assertEqual(reopened["state"], "VALIDATION_FAILED")
        self.assertEqual(reopened["validations"][0]["status"], "FAILED")
        self.assertNotEqual(reopened["state"], "COMPLETE")

    def test_sha256_criterion_is_deterministic(self) -> None:
        digest = hashlib.sha256(b"hash me").hexdigest()
        task = self.create_task("hash", digest, criterion_type="SHA256")
        _, artifact = self.produce(task, "hash", "hash me")
        result = self.validator.validate(task_id=task["task_id"], artifact_id=artifact["artifact_id"],
            source_request_id="validation:hash")
        self.assertEqual(result["status"], "PASSED")

    def test_wp3_database_migration_preserves_task_artifact_and_attempt(self) -> None:
        legacy = self.root / "wp3.db"
        with closing(sqlite3.connect(legacy)) as conn:
            conn.executescript("""
                CREATE TABLE owner_tasks (task_id TEXT PRIMARY KEY, source_request_id TEXT NOT NULL UNIQUE,
                  owner_id TEXT NOT NULL, objective TEXT NOT NULL, authority_id TEXT NOT NULL, state TEXT NOT NULL,
                  assigned_agent TEXT, workspace_id TEXT, assignment_authority_id TEXT, assignment_source TEXT,
                  assigned_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE execution_attempts (attempt_id TEXT PRIMARY KEY, source_request_id TEXT NOT NULL UNIQUE,
                  source_event_id INTEGER, idempotency_key TEXT NOT NULL UNIQUE, authority_id TEXT NOT NULL,
                  agent_id TEXT NOT NULL, workspace_id TEXT NOT NULL, requested_operation TEXT NOT NULL,
                  task_id TEXT, created_at TEXT NOT NULL, request_json TEXT NOT NULL, state TEXT NOT NULL,
                  generation INTEGER NOT NULL DEFAULT 0, owner_id TEXT, lease_expiry TEXT, started_at TEXT,
                  outcome_json TEXT, audit_id INTEGER, published_event_id INTEGER, acknowledged_at TEXT,
                  updated_at TEXT NOT NULL);
                CREATE TABLE owner_task_artifacts (task_id TEXT NOT NULL, attempt_id TEXT NOT NULL,
                  reference TEXT NOT NULL, created_at TEXT NOT NULL,
                  PRIMARY KEY(task_id, attempt_id, reference));
            """)
            now = iso_now()
            conn.execute("INSERT INTO owner_tasks (task_id,source_request_id,owner_id,objective,authority_id,state,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                ("task-old", "owner-old", "owner", "old", "authority:old", "READY_FOR_VALIDATION", now, now))
            conn.execute("INSERT INTO execution_attempts (attempt_id,source_request_id,idempotency_key,authority_id,agent_id,workspace_id,requested_operation,task_id,created_at,request_json,state,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ("attempt-old", "execution-old", "key-old", "authority:old", "command", self.workspace_id,
                 "WRITE_FILE", "task-old", now, "{}", "SUCCEEDED", now))
            conn.execute("INSERT INTO owner_task_artifacts VALUES (?,?,?,?)",
                ("task-old", "attempt-old", "old.txt", now))
            conn.commit()
        migrated = SQLiteMailStore(legacy)
        observed = migrated.get_owner_task("task-old")
        self.assertEqual(observed["attempts"][0]["attempt_id"], "attempt-old")
        self.assertEqual(observed["artifacts"][0]["reference"], "old.txt")
        self.assertIn("artifact_id", observed["artifacts"][0])
        self.assertEqual(SQLiteMailStore(legacy).get_owner_task("task-old")["state"],
                         "READY_FOR_VALIDATION")


if __name__ == "__main__":
    unittest.main()
