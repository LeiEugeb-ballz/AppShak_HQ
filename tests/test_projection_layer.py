from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from appshak_projection.projector import ProjectionProjector
from appshak_projection.view_store import ProjectionViewStore
from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.types import SubstrateEvent


class TestProjectionViewStore(unittest.TestCase):
    def test_atomic_save_and_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_projection_store_") as temp_dir:
            view_path = Path(temp_dir) / "projection" / "view.json"
            store = ProjectionViewStore(view_path)
            persisted = store.save(
                {
                    "schema_version": 1,
                    "running": True,
                    "event_queue_size": 3,
                    "last_seen_event_id": 12,
                    "last_seen_tool_audit_id": 4,
                    "tool_audit_counts": {"allowed": 2, "denied": 1},
                    "timestamp": "2026-02-27T00:00:00+00:00",
                }
            )

            self.assertTrue(view_path.exists())
            self.assertEqual(list(view_path.parent.glob("*.tmp")), [])

            loaded = store.load()
            self.assertEqual(loaded["schema_version"], 1)
            self.assertEqual(loaded["running"], True)
            self.assertEqual(loaded["event_queue_size"], 3)
            self.assertEqual(loaded["last_seen_event_id"], 12)
            self.assertEqual(loaded["last_seen_tool_audit_id"], 4)
            self.assertEqual(loaded["tool_audit_counts"]["allowed"], 2)
            self.assertEqual(loaded["tool_audit_counts"]["denied"], 1)
            self.assertEqual(loaded["timestamp"], "2026-02-27T00:00:00+00:00")
            self.assertEqual(loaded, persisted)


class TestProjectionProjector(unittest.TestCase):
    def test_cursor_resume_avoids_double_counting(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_projection_resume_") as temp_dir:
            db_path = Path(temp_dir) / "mailstore.db"
            view_path = Path(temp_dir) / "view.json"
            mail_store = SQLiteMailStore(db_path)
            view_store = ProjectionViewStore(view_path)

            mail_store.append_event(SubstrateEvent(type="INTENT_DISPATCH", origin_id="intent", payload={}))

            projector = ProjectionProjector(mail_store=mail_store, view_store=view_store)
            first = projector.project_once()
            self.assertEqual(first["events_processed"], 1)
            self.assertEqual(first["last_seen_event_id"], 1)
            self.assertEqual(first["event_type_counts"]["INTENT_DISPATCH"], 1)

            resumed = ProjectionProjector(mail_store=mail_store, view_store=view_store)
            second = resumed.project_once()
            self.assertEqual(second["events_processed"], 1)
            self.assertEqual(second["event_type_counts"]["INTENT_DISPATCH"], 1)

            mail_store.append_event(SubstrateEvent(type="INTENT_DISPATCH", origin_id="intent", payload={}))
            third = resumed.project_once()
            self.assertEqual(third["events_processed"], 2)
            self.assertEqual(third["last_seen_event_id"], 2)
            self.assertEqual(third["event_type_counts"]["INTENT_DISPATCH"], 2)

    def test_running_state_derived_from_supervisor_start_stop(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_projection_running_") as temp_dir:
            db_path = Path(temp_dir) / "mailstore.db"
            view_path = Path(temp_dir) / "view.json"
            mail_store = SQLiteMailStore(db_path)
            view_store = ProjectionViewStore(view_path)
            projector = ProjectionProjector(mail_store=mail_store, view_store=view_store)

            mail_store.append_event(SubstrateEvent(type="SUPERVISOR_START", origin_id="supervisor", payload={}))
            after_start = projector.project_once()
            self.assertTrue(after_start["running"])

            mail_store.append_event(SubstrateEvent(type="SUPERVISOR_STOP", origin_id="supervisor", payload={}))
            after_stop = projector.project_once()
            self.assertFalse(after_stop["running"])

    def test_tool_audit_allowed_denied_counters_increment(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_projection_audit_") as temp_dir:
            db_path = Path(temp_dir) / "mailstore.db"
            view_path = Path(temp_dir) / "view.json"
            mail_store = SQLiteMailStore(db_path)
            view_store = ProjectionViewStore(view_path)
            projector = ProjectionProjector(mail_store=mail_store, view_store=view_store)

            mail_store.append_tool_audit(
                agent_id="recon",
                action_type="RUN_CMD",
                working_dir=temp_dir,
                idempotency_key="audit-1",
                allowed=True,
                reason="ok",
                payload={"argv": ["echo", "ok"]},
                result={"return_code": 0},
            )
            mail_store.append_tool_audit(
                agent_id="recon",
                action_type="RUN_CMD",
                working_dir=temp_dir,
                idempotency_key="audit-2",
                allowed=False,
                reason="blocked",
                payload={"argv": ["rm", "-rf", "/"]},
                result={"return_code": 1},
            )
            mail_store.append_tool_audit(
                agent_id="command",
                action_type="WRITE_FILE",
                working_dir=temp_dir,
                idempotency_key="audit-3",
                allowed=False,
                reason="blocked",
                payload={"path": "secret.txt"},
                result={"error": "denied"},
            )

            projected = projector.project_once()
            self.assertEqual(projected["last_seen_tool_audit_id"], 3)
            self.assertEqual(projected["tool_audit_counts"]["allowed"], 1)
            self.assertEqual(projected["tool_audit_counts"]["denied"], 2)

    def test_worker_state_transitions_started_restarting_restarted_exited(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_projection_workers_") as temp_dir:
            db_path = Path(temp_dir) / "mailstore.db"
            view_path = Path(temp_dir) / "view.json"
            mail_store = SQLiteMailStore(db_path)
            view_store = ProjectionViewStore(view_path)
            projector = ProjectionProjector(mail_store=mail_store, view_store=view_store)

            mail_store.append_event(
                SubstrateEvent(type="WORKER_STARTED", origin_id="supervisor", payload={"agent_id": "recon"})
            )
            after_started = projector.project_once()
            recon_worker = after_started["workers"]["recon"]
            self.assertTrue(recon_worker["present"])
            self.assertEqual(recon_worker["state"], "ACTIVE")
            self.assertEqual(recon_worker["restart_count"], 0)
            self.assertEqual(recon_worker["last_event_type"], "WORKER_STARTED")
            self.assertIsInstance(recon_worker["last_event_at"], str)
            self.assertEqual(recon_worker["last_seen_event_id"], 1)

            mail_store.append_event(
                SubstrateEvent(type="WORKER_RESTART_SCHEDULED", origin_id="supervisor", payload={"agent_id": "recon"})
            )
            after_restart_scheduled = projector.project_once()
            recon_worker = after_restart_scheduled["workers"]["recon"]
            self.assertEqual(recon_worker["state"], "RESTARTING")
            self.assertEqual(recon_worker["last_event_type"], "WORKER_RESTART_SCHEDULED")
            self.assertEqual(recon_worker["last_seen_event_id"], 2)

            mail_store.append_event(
                SubstrateEvent(type="WORKER_RESTARTED", origin_id="supervisor", payload={"agent_id": "recon"})
            )
            after_restarted = projector.project_once()
            recon_worker = after_restarted["workers"]["recon"]
            self.assertTrue(recon_worker["present"])
            self.assertEqual(recon_worker["state"], "ACTIVE")
            self.assertEqual(recon_worker["restart_count"], 1)
            self.assertEqual(recon_worker["last_event_type"], "WORKER_RESTARTED")
            self.assertEqual(recon_worker["last_seen_event_id"], 3)

            mail_store.append_event(
                SubstrateEvent(type="WORKER_EXITED", origin_id="supervisor", payload={"agent_id": "recon"})
            )
            after_exited = projector.project_once()
            recon_worker = after_exited["workers"]["recon"]
            self.assertFalse(recon_worker["present"])
            self.assertEqual(recon_worker["state"], "OFFLINE")
            self.assertEqual(recon_worker["last_event_type"], "WORKER_EXITED")
            self.assertEqual(recon_worker["last_seen_event_id"], 4)

    def test_worker_heartbeat_missed_increments_and_offline_threshold(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_projection_heartbeat_") as temp_dir:
            db_path = Path(temp_dir) / "mailstore.db"
            view_path = Path(temp_dir) / "view.json"
            mail_store = SQLiteMailStore(db_path)
            view_store = ProjectionViewStore(view_path)
            projector = ProjectionProjector(mail_store=mail_store, view_store=view_store)

            mail_store.append_event(
                SubstrateEvent(type="WORKER_STARTED", origin_id="supervisor", payload={"agent_id": "forge"})
            )
            projector.project_once()

            mail_store.append_event(
                SubstrateEvent(type="WORKER_HEARTBEAT_MISSED", origin_id="supervisor", payload={"agent_id": "forge"})
            )
            after_first_miss = projector.project_once()
            forge_worker = after_first_miss["workers"]["forge"]
            self.assertEqual(forge_worker["missed_heartbeat_count"], 1)
            self.assertNotEqual(forge_worker["state"], "OFFLINE")
            self.assertEqual(forge_worker["last_event_type"], "WORKER_HEARTBEAT_MISSED")
            self.assertEqual(forge_worker["last_seen_event_id"], 2)

            mail_store.append_event(
                SubstrateEvent(type="WORKER_HEARTBEAT_MISSED", origin_id="supervisor", payload={"agent_id": "forge"})
            )
            after_second_miss = projector.project_once()
            forge_worker = after_second_miss["workers"]["forge"]
            self.assertEqual(forge_worker["missed_heartbeat_count"], 2)
            self.assertEqual(forge_worker["state"], "OFFLINE")
            self.assertFalse(forge_worker["present"])
            self.assertEqual(forge_worker["last_seen_event_id"], 3)

    def test_derived_stress_level_normalization(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_projection_derived_") as temp_dir:
            db_path = Path(temp_dir) / "mailstore.db"
            view_path = Path(temp_dir) / "view.json"
            mail_store = SQLiteMailStore(db_path)
            view_store = ProjectionViewStore(view_path)
            projector = ProjectionProjector(mail_store=mail_store, view_store=view_store)

            for _ in range(10):
                mail_store.append_event(SubstrateEvent(type="INTENT_DISPATCH", origin_id="intent", payload={}))
            low_stress = projector.project_once()
            self.assertEqual(low_stress["event_queue_size"], 10)
            self.assertEqual(low_stress["derived"]["office_mode"], "PAUSED")
            self.assertAlmostEqual(low_stress["derived"]["stress_level"], 0.4, places=6)

            for _ in range(20):
                mail_store.append_event(SubstrateEvent(type="INTENT_DISPATCH", origin_id="intent", payload={}))
            high_stress = projector.project_once()
            self.assertEqual(high_stress["event_queue_size"], 30)
            self.assertAlmostEqual(high_stress["derived"]["stress_level"], 1.0, places=6)

            mail_store.append_event(SubstrateEvent(type="SUPERVISOR_START", origin_id="supervisor", payload={}))
            running = projector.project_once()
            self.assertTrue(running["running"])
            self.assertEqual(running["derived"]["office_mode"], "RUNNING")


if __name__ == "__main__":
    unittest.main()
