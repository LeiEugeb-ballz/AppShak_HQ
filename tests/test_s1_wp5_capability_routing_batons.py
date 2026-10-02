from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from appshak_substrate.artifact_validator import ArtifactValidator
from appshak_substrate.baton_routing import CAPABILITIES, CapabilityRoutingPolicy, RouteTarget, VerifiedBatonManager
from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.policy import ToolPolicy
from appshak_substrate.tool_gateway import ToolGateway
from appshak_substrate.types import iso_now


class TestCapabilityRoutingBatons(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="appshak_wp5_")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.worktree = root / "worker"
        self.worktree.mkdir()
        self.db = root / "mail.db"
        self.repo = root / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "wp5-review@example.invalid"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "WP5 Review"], cwd=self.repo, check=True)
        (self.repo / "evidence.md").write_text("verified evidence\n", encoding="utf-8")
        subprocess.run(["git", "add", "evidence.md"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=self.repo, check=True)
        self.store = SQLiteMailStore(self.db, lease_seconds=0.3, poll_interval=0.01)
        workspace_id = ToolGateway.workspace_identity("command", self.worktree)
        self.gateway = ToolGateway(mail_store=self.store, policy=ToolPolicy(chief_agent_id="command"),
            workspace_roots={"command": self.worktree}, command_timeout_seconds=3)
        self.validator = ArtifactValidator(mail_store=self.store, tool_gateway=self.gateway)
        self.workspace_id = workspace_id
        self.manager = VerifiedBatonManager(self.store, self.repo)
        self.head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()

    @staticmethod
    def _policy() -> CapabilityRoutingPolicy:
        return CapabilityRoutingPolicy((RouteTarget(
            "configured-test-worker", tuple(sorted(CAPABILITIES)),
            "test-provider-class", "test-model-class",
        ),), version="test-policy-v1")

    def _complete_task(self, name: str = "task") -> tuple[dict, dict]:
        task = self.store.create_owner_task(owner_id="owner", objective=f"Produce {name}",
            authority_id=f"authority:{name}", source_request_id=f"owner:{name}")
        self.store.add_acceptance_criterion(task_id=task["task_id"], criterion_type="EXACT_TEXT",
            config={"expected": "done"}, created_by="owner", source_ref=f"acceptance:{name}")
        task = self.store.assign_owner_task(task_id=task["task_id"], agent_id="command",
            workspace_id=self.workspace_id, authority_id=task["authority_id"], actor_id="owner",
            source_ref=f"assignment:{name}")
        result = self.gateway.execute({"task_id": task["task_id"], "agent_id": "command",
            "authorized_by": "command", "action_type": "WRITE_FILE", "working_dir": str(self.worktree),
            "authority_id": task["authority_id"], "source_request_id": f"production:{name}",
            "workspace_id": self.workspace_id, "requested_operation": "WRITE_FILE", "created_at": iso_now(),
            "payload": {"path": f"{name}.txt", "content": "done", "idempotency_key": f"production:{name}"}})
        self.assertTrue(result.allowed, result.reason)
        task = self.store.get_owner_task(task["task_id"])
        artifact = task["artifacts"][0]
        validation = self.validator.validate(task_id=task["task_id"], artifact_id=artifact["artifact_id"],
            source_request_id=f"validation:{name}")
        self.assertEqual(validation["status"], "PASSED")
        return task, validation

    def _baton(self, baton_id: str = "BATON-TEST", *, source: str | None = None,
               capability: str = "INTEGRATION", task: dict | None = None,
               validation: dict | None = None, commit: str | None = None) -> dict:
        task = task or self._complete_task(baton_id)[0]
        validation = validation or self.store.get_owner_task(task["task_id"])["validations"][0]
        return self.manager.create_baton(baton_id=baton_id, source_baton_id=source,
            task_id=task["task_id"], work_package="S1-WP5 verified source work",
            next_objective="S1-WP6 next objective", git_commit=commit or self.head,
            completion_status="COMPLETE", current_state={"task_state": "COMPLETE"}, results={"tests": "PASS"},
            evidence_references=["evidence.md"],
            validation_id=validation["validation_id"], required_capability=capability,
            producer_id="test:wp5")

    def test_required_capability_catalog_is_complete(self) -> None:
        self.assertEqual(len(CAPABILITIES), 8)
        self.assertIn("CERTIFICATION", CAPABILITIES)

    def test_candidate_schema_migrates_without_losing_baton_table(self) -> None:
        legacy_db = Path(self.temp.name) / "candidate.db"
        with closing(sqlite3.connect(legacy_db)) as conn:
            conn.execute("""CREATE TABLE capability_batons (
                baton_id TEXT PRIMARY KEY, source_baton_id TEXT, task_id TEXT NOT NULL,
                work_package TEXT NOT NULL, repository_root TEXT NOT NULL, git_commit TEXT NOT NULL,
                completion_status TEXT NOT NULL, current_state_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL, validation_id TEXT, required_capability TEXT NOT NULL,
                created_at TEXT NOT NULL, producer_id TEXT NOT NULL, verification_status TEXT NOT NULL,
                status TEXT NOT NULL, verification_reason TEXT, verification_evidence_json TEXT,
                policy_version TEXT, updated_at TEXT NOT NULL
            )""")
        SQLiteMailStore(legacy_db)
        with closing(sqlite3.connect(legacy_db)) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(capability_batons)")}
        self.assertTrue({"working_tree_hash", "next_objective", "results_json"} <= columns)

    def test_unvalidated_completion_is_rejected(self) -> None:
        task = self.store.create_owner_task(owner_id="owner", objective="incomplete",
            authority_id="authority:incomplete", source_request_id="owner:incomplete")
        fake = self.manager.create_baton(baton_id="BATON-INCOMPLETE", source_baton_id=None,
            task_id=task["task_id"], work_package="source", next_objective="next",
            git_commit=self.head, completion_status="COMPLETE",
            current_state={"task_state": "COMPLETE"}, results={"tests": "PASS"}, evidence_references=["evidence.md"],
            validation_id="missing-validation", required_capability="VALIDATION_IMPLEMENTATION", producer_id="test")
        checked = self.manager.verify_baton(fake["baton_id"])
        self.assertEqual(checked["status"], "REJECTED")

    def test_verified_baton_requires_real_git_basis(self) -> None:
        task, validation = self._complete_task("stale-git")
        baton = self._baton("BATON-STALE", task=task, validation=validation, commit="0" * 40)
        self.assertEqual(self.manager.verify_baton(baton["baton_id"])["status"], "REJECTED")

    def test_missing_evidence_is_rejected(self) -> None:
        task, validation = self._complete_task("missing-evidence")
        baton = self.manager.create_baton(baton_id="BATON-EVIDENCE", source_baton_id=None,
            task_id=task["task_id"], work_package="source", next_objective="next",
            git_commit=self.head, completion_status="COMPLETE",
            current_state={"task_state": "COMPLETE"}, results={"tests": "PASS"}, evidence_references=["missing/evidence.md"],
            validation_id=validation["validation_id"], required_capability="INTEGRATION", producer_id="test")
        self.assertEqual(self.manager.verify_baton(baton["baton_id"])["status"], "REJECTED")

    def test_evidence_cannot_escape_repository(self) -> None:
        outside = self.repo.parent / "outside.md"
        outside.write_text("not repository evidence", encoding="utf-8")
        task, validation = self._complete_task("outside-evidence")
        baton = self.manager.create_baton(baton_id="BATON-OUTSIDE", source_baton_id=None,
            task_id=task["task_id"], work_package="source", next_objective="next",
            git_commit=self.head, completion_status="COMPLETE",
            current_state={"task_state": "COMPLETE"}, results={"tests": "PASS"}, evidence_references=["../outside.md"],
            validation_id=validation["validation_id"], required_capability="INTEGRATION", producer_id="test")
        self.assertEqual(self.manager.verify_baton(baton["baton_id"])["status"], "REJECTED")

    def test_fabricated_current_state_is_rejected(self) -> None:
        task, validation = self._complete_task("false-state")
        baton = self.manager.create_baton(baton_id="BATON-FALSE-STATE", source_baton_id=None,
            task_id=task["task_id"], work_package="source", next_objective="next",
            git_commit=self.head, completion_status="COMPLETE",
            current_state={"task_state": "FAILED"}, results={"tests": "PASS"}, evidence_references=["evidence.md"],
            validation_id=validation["validation_id"], required_capability="INTEGRATION", producer_id="test")
        self.assertEqual(self.manager.verify_baton(baton["baton_id"])["status"], "REJECTED")

    def test_verified_baton_persists_across_restart(self) -> None:
        baton = self._baton("BATON-RESTART")
        self.assertEqual(self.manager.verify_baton(baton["baton_id"])["status"], "VERIFIED")
        reopened = VerifiedBatonManager(SQLiteMailStore(self.db), self.repo)
        self.assertEqual(reopened.get_baton(baton["baton_id"])["status"], "VERIFIED")

    def test_verified_source_lineage_persists(self) -> None:
        parent = self._baton("BATON-PARENT")
        self.assertEqual(self.manager.verify_baton(parent["baton_id"])["status"], "VERIFIED")
        child = self._baton("BATON-CHILD", source=parent["baton_id"])
        self.assertEqual(self.manager.verify_baton(child["baton_id"])["status"], "VERIFIED")
        reopened = VerifiedBatonManager(SQLiteMailStore(self.db), self.repo)
        self.assertEqual(reopened.get_baton(parent["baton_id"])["status"], "SUPERSEDED")
        self.assertEqual(reopened.get_baton(child["baton_id"])["source_baton_id"], parent["baton_id"])

    def test_filesystem_json_cannot_auto_verify_lineage(self) -> None:
        baton_dir = self.repo / ".appshak" / "batons"
        baton_dir.mkdir(parents=True)
        (baton_dir / "BATON-FAKE-anything.json").write_text(json.dumps({
            "baton_id": "BATON-FAKE", "completion_status": "PASS"
        }), encoding="utf-8")
        child = self._baton("BATON-FAKE-CHILD", source="BATON-FAKE")
        self.assertEqual(self.manager.verify_baton(child["baton_id"])["status"], "REJECTED")

    def test_obsolete_source_cannot_branch(self) -> None:
        parent = self._baton("BATON-BRANCH-PARENT")
        self.manager.verify_baton(parent["baton_id"])
        first = self._baton("BATON-BRANCH-FIRST", source=parent["baton_id"])
        self.assertEqual(self.manager.verify_baton(first["baton_id"])["status"], "VERIFIED")
        second = self._baton("BATON-BRANCH-SECOND", source=parent["baton_id"])
        self.assertEqual(self.manager.verify_baton(second["baton_id"])["status"], "REJECTED")

    def test_invalid_source_lineage_rejects(self) -> None:
        baton = self._baton("BATON-BAD-LINEAGE", source="BATON-NOT-FOUND")
        self.assertEqual(self.manager.verify_baton(baton["baton_id"])["status"], "REJECTED")

    def test_policy_route_is_deterministic(self) -> None:
        policy = CapabilityRoutingPolicy((
            RouteTarget("z-worker", ("INTEGRATION",), "provider-z", "model-z", priority=10),
            RouteTarget("a-worker", ("INTEGRATION",), "provider-a", "model-a", priority=10),
        ))
        self.assertEqual(policy.resolve("integration")["target_id"], "a-worker")
        self.assertEqual(policy.resolve("integration"), policy.resolve("INTEGRATION"))

    def test_unknown_capability_has_no_route(self) -> None:
        self.assertIsNone(CapabilityRoutingPolicy.default().resolve("UNKNOWN"))

    def test_default_policy_fails_closed_without_configured_target(self) -> None:
        self.assertIsNone(CapabilityRoutingPolicy.default().resolve("INTEGRATION"))

    def test_provider_and_model_are_policy_metadata(self) -> None:
        baton = self._baton("BATON-SEPARATION", capability="IMPLEMENTATION")
        self.manager.verify_baton(baton["baton_id"])
        dispatch = self.manager.dispatch(baton["baton_id"], self._policy())
        self.assertNotIn("provider_class", baton)
        self.assertEqual(dispatch["route"]["provider_class"], "test-provider-class")

    def test_dispatch_records_one_durable_external_dispatch(self) -> None:
        baton = self._baton("BATON-DISPATCH")
        self.manager.verify_baton(baton["baton_id"])
        first = self.manager.dispatch(baton["baton_id"], self._policy())
        reopened = VerifiedBatonManager(SQLiteMailStore(self.db), self.repo)
        second = reopened.dispatch(baton["baton_id"], self._policy())
        self.assertEqual(first["status"], "READY_FOR_EXTERNAL_DISPATCH")
        self.assertEqual(first["dispatch_id"], second["dispatch_id"])
        self.assertEqual(first["route"], second["route"])

    def test_no_eligible_target_waits_without_fake_dispatch(self) -> None:
        baton = self._baton("BATON-WAIT", capability="CERTIFICATION")
        self.manager.verify_baton(baton["baton_id"])
        policy = CapabilityRoutingPolicy((RouteTarget("other", ("IMPLEMENTATION",), "p", "m"),))
        dispatch = self.manager.dispatch(baton["baton_id"], policy)
        self.assertEqual(dispatch["status"], "WAITING_FOR_CAPABILITY")
        self.assertIsNone(dispatch["target_id"])

    def test_unauthorized_requested_target_waits(self) -> None:
        baton = self._baton("BATON-AUTH-TARGET")
        self.manager.verify_baton(baton["baton_id"])
        dispatch = self.manager.dispatch(baton["baton_id"], self._policy(),
            requested_target="not-configured")
        self.assertEqual(dispatch["status"], "WAITING_FOR_CAPABILITY")

    def test_context_pack_contains_next_objective_and_evidence(self) -> None:
        baton = self._baton("BATON-CONTEXT")
        self.manager.verify_baton(baton["baton_id"])
        dispatch = self.manager.dispatch(baton["baton_id"], self._policy())
        self.assertEqual(dispatch["context"]["work_package"], "S1-WP5 verified source work")
        self.assertEqual(dispatch["context"]["next_objective"], "S1-WP6 next objective")
        self.assertEqual(dispatch["context"]["results"], {"tests": "PASS"})
        self.assertTrue(dispatch["context"]["evidence_references"])

    def test_superseded_baton_cannot_dispatch(self) -> None:
        baton = self._baton("BATON-SUPERSEDE")
        self.manager.verify_baton(baton["baton_id"])
        self.manager.supersede(baton["baton_id"])
        with self.assertRaisesRegex(ValueError, "VERIFIED"):
            self.manager.dispatch(baton["baton_id"], self._policy())

    def test_rejected_baton_cannot_dispatch(self) -> None:
        baton = self._baton("BATON-REJECT-DISPATCH", commit="0" * 40)
        self.assertEqual(self.manager.verify_baton(baton["baton_id"])["status"], "REJECTED")
        with self.assertRaisesRegex(ValueError, "VERIFIED"):
            self.manager.dispatch(baton["baton_id"], self._policy())

    def test_working_tree_drift_rejects_baton(self) -> None:
        baton = self._baton("BATON-TREE-DRIFT")
        (self.repo / "drift.txt").write_text("changed after creation\n", encoding="utf-8")
        checked = self.manager.verify_baton(baton["baton_id"])
        self.assertEqual(checked["status"], "REJECTED")
        self.assertIn("working-tree basis", checked["verification_reason"])

    def test_current_projection_is_only_a_filesystem_projection(self) -> None:
        baton = self._baton("BATON-PROJECTION")
        self.manager.verify_baton(baton["baton_id"])
        path = Path(self.temp.name) / ".appshak" / "CURRENT_BATON.json"
        projection = self.manager.write_current_projection(path, baton["baton_id"])
        self.assertEqual(json.loads(path.read_text())["canonical_state"], "sqlite:capability_batons")
        self.assertEqual(projection["baton_id"], baton["baton_id"])


if __name__ == "__main__":
    unittest.main()
