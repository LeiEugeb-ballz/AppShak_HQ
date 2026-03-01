from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from appshak_inspection.indexer import build_inspection_index, paginate_timeline
from appshak_inspection.store import InspectionIndexStore
from appshak_integrity.report import build_integrity_report
from appshak_integrity.store import IntegrityReportStore
from appshak_integrity.utils import canonical_hash
from appshak_observability.server import create_app
from appshak_observability.stores import ObservabilityDataStore
from appshak_projection.view_store import ProjectionViewStore
from appshak_stability.store import StabilityRunStore


def _synthetic_projection_snapshot() -> dict:
    return {
        "schema_version": 1,
        "timestamp": "2026-03-01T12:00:05+00:00",
        "running": True,
        "event_queue_size": 3,
        "last_seen_event_id": 5,
        "last_seen_tool_audit_id": 2,
        "events_processed": 5,
        "current_event": {
            "type": "INTENT_DISPATCH",
            "timestamp": "2026-03-01T12:00:05+00:00",
            "origin_id": "supervisor",
            "payload": {"target_agent": "recon"},
        },
        "workers": {
            "recon": {
                "present": True,
                "state": "ACTIVE",
                "last_event_type": "INTENT_DISPATCH",
                "last_event_at": "2026-03-01T12:00:05+00:00",
                "restart_count": 1,
                "missed_heartbeat_count": 0,
            },
            "forge": {
                "present": True,
                "state": "IDLE",
                "last_event_type": "WORKER_STARTED",
                "last_event_at": "2026-03-01T12:00:03+00:00",
                "restart_count": 0,
                "missed_heartbeat_count": 1,
            },
        },
        "tool_audit_counts": {"allowed": 2, "denied": 1},
        "event_type_counts": {"INTENT_DISPATCH": 3, "SUPERVISOR_START": 1},
        "derived": {"office_mode": "RUNNING", "stress_level": 0.12},
    }


def _synthetic_governance_entries() -> list[dict]:
    return [
        {
            "seq": 1,
            "entry_type": "WATER_COOLER_LESSON",
            "timestamp": "2026-03-01T12:00:01+00:00",
            "payload": {
                "triggered": True,
                "lesson": {
                    "lesson_id": "LESSON-001",
                    "source_agent": "supervisor",
                    "recipients": ["recon", "forge"],
                },
            },
        },
        {
            "seq": 2,
            "entry_type": "TRUST_CHANGE",
            "timestamp": "2026-03-01T12:00:02+00:00",
            "payload": {
                "subject_id": "recon",
                "agent_id": "recon",
                "outcome": "SUCCESS",
                "reputation_delta": 0.06,
                "source_event_id": 2,
                "source_event_type": "INTENT_DISPATCH",
                "source_timestamp": "2026-03-01T12:00:02+00:00",
                "note": "LESSON-001",
            },
        },
        {
            "seq": 3,
            "entry_type": "ARBITRATION_OUTCOME",
            "timestamp": "2026-03-01T12:00:03+00:00",
            "payload": {
                "target_agent": "forge",
                "approved": True,
                "aggregate_score": 0.66,
                "revisions_before_execute": 1,
                "previous_aggregate_score": 0.52,
                "source_event_id": 3,
                "votes": [
                    {"agent_id": "supervisor", "reasoning_score": 0.9},
                    {"agent_id": "recon", "reasoning_score": 0.8},
                ],
                "references": {"lesson": "LESSON-001"},
            },
        },
        {
            "seq": 4,
            "entry_type": "TRUST_STABILITY_METRIC",
            "timestamp": "2026-03-01T12:00:04+00:00",
            "payload": {
                "global_variance": 0.011,
                "window_size": 5,
            },
        },
        {
            "seq": 5,
            "entry_type": "REGISTRY_UPDATE",
            "timestamp": "2026-03-01T12:00:05+00:00",
            "payload": {
                "registry_hash": "abc",
                "registry": {
                    "version": 9,
                    "last_updated": "2026-03-01T12:00:05+00:00",
                    "agents": {
                        "recon": {
                            "agent_id": "recon",
                            "role": "recon",
                            "authority_level": 0.7,
                            "reputation_score": 0.61,
                            "trust_weights": {"recon": 0.5, "forge": 0.45},
                            "knowledge_lessons": ["LESSON-001"],
                        },
                        "forge": {
                            "agent_id": "forge",
                            "role": "forge",
                            "authority_level": 0.6,
                            "reputation_score": 0.52,
                            "trust_weights": {"recon": 0.53, "forge": 0.5},
                            "knowledge_lessons": [],
                        },
                    },
                    "history": {
                        "recon": [0.5, 0.56, 0.61],
                        "forge": [0.5, 0.52],
                    },
                },
            },
        },
    ]


class TestPhase4IntegrityAndInspection(unittest.TestCase):
    def test_integrity_report_determinism_same_input_same_hash(self) -> None:
        snapshot = _synthetic_projection_snapshot()
        entries = _synthetic_governance_entries()
        report_a = build_integrity_report(
            window="7d",
            projection_snapshot=snapshot,
            governance_entries=entries,
            replay_result={"hashes_equal": True, "chain_valid": True},
            generated_at="2026-03-01T13:00:00+00:00",
        )
        report_b = build_integrity_report(
            window="7d",
            projection_snapshot=snapshot,
            governance_entries=entries,
            replay_result={"hashes_equal": True, "chain_valid": True},
            generated_at="2026-03-01T13:00:00+00:00",
        )
        self.assertEqual(report_a, report_b)
        self.assertEqual(canonical_hash(report_a), canonical_hash(report_b))

    def test_knowledge_propagation_velocity_determinism(self) -> None:
        report = build_integrity_report(
            window="7d",
            projection_snapshot=_synthetic_projection_snapshot(),
            governance_entries=_synthetic_governance_entries(),
            generated_at="2026-03-01T13:00:00+00:00",
        )
        propagation = report["propagation"]
        self.assertEqual(propagation["mode"], "explicit_lessons")
        self.assertEqual(propagation["lessons_total"], 1)
        self.assertAlmostEqual(propagation["time_to_reuse"]["mean"], 1.0, places=6)
        self.assertGreaterEqual(propagation["knowledge_propagation_velocity"], 0.0)

    def test_inspection_index_determinism(self) -> None:
        snapshot = _synthetic_projection_snapshot()
        entries = _synthetic_governance_entries()
        integrity = build_integrity_report(
            window="7d",
            projection_snapshot=snapshot,
            governance_entries=entries,
            generated_at="2026-03-01T13:00:00+00:00",
        )
        index_a = build_inspection_index(
            projection_snapshot=snapshot,
            governance_entries=entries,
            integrity_report=integrity,
        )
        index_b = build_inspection_index(
            projection_snapshot=snapshot,
            governance_entries=entries,
            integrity_report=integrity,
        )
        self.assertEqual(index_a, index_b)
        self.assertEqual(index_a["index_hash"], index_b["index_hash"])

    def test_timeline_pagination_stability_no_overlap_no_gap(self) -> None:
        timeline = [{"event_id": index, "entry_type": "X"} for index in range(1, 16)]
        cursor = None
        seen = []
        while True:
            page = paginate_timeline(timeline, limit=4, cursor=cursor)
            items = page["items"]
            seen.extend([item["event_id"] for item in items])
            cursor = page["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(seen, list(range(1, 16)))

    def test_inspection_and_integrity_api_contracts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="phase4_api_") as temp_dir:
            temp_root = Path(temp_dir)
            projection_path = temp_root / "projection" / "view.json"
            governance_entries = _synthetic_governance_entries()
            snapshot = _synthetic_projection_snapshot()
            projection_store = ProjectionViewStore(projection_path)
            projection_store.save(snapshot)

            integrity_report = build_integrity_report(
                window="7d",
                projection_snapshot=snapshot,
                governance_entries=governance_entries,
                generated_at="2026-03-01T13:00:00+00:00",
            )
            integrity_store = IntegrityReportStore(temp_root / "integrity")
            integrity_store.save(integrity_report)

            inspection_index = build_inspection_index(
                projection_snapshot=snapshot,
                governance_entries=governance_entries,
                integrity_report=integrity_report,
            )
            inspection_store = InspectionIndexStore(temp_root / "inspection")
            inspection_store.save(inspection_index)

            stability_store = StabilityRunStore(temp_root / "stability")
            run_dir = stability_store.init_run(
                run_id="run_test",
                meta={
                    "run_id": "run_test",
                    "status": "completed",
                    "started_at": "2026-03-01T13:00:00+00:00",
                    "updated_at": "2026-03-01T13:01:00+00:00",
                },
            )
            stability_store.checkpoint(
                run_dir=run_dir,
                checkpoint_id=1,
                payload={"checkpoint_id": 1, "timestamp": "2026-03-01T13:01:00+00:00"},
            )

            app = create_app(
                projection_view_store=projection_store,
                data_store=ObservabilityDataStore(
                    inspection_root=temp_root / "inspection",
                    integrity_root=temp_root / "integrity",
                    stability_root=temp_root / "stability",
                ),
            )

            route_map = {route.path: route for route in app.routes if hasattr(route, "path")}
            snapshot_payload = _model_to_dict(asyncio.run(route_map["/api/snapshot"].endpoint()))
            self.assertEqual(sorted(snapshot_payload.keys()), ["current_event", "event_queue_size", "running", "timestamp"])

            entities_payload = asyncio.run(route_map["/api/inspect/entities"].endpoint())
            self.assertIn("items", entities_payload)
            self.assertGreaterEqual(entities_payload["count"], 1)

            entity_payload = asyncio.run(route_map["/api/inspect/entity/{entity_id}"].endpoint("recon"))
            self.assertEqual(entity_payload.get("id"), "recon")

            entity_timeline_payload = asyncio.run(
                route_map["/api/inspect/entity/{entity_id}/timeline"].endpoint("recon", limit=5, cursor=None)
            )
            self.assertIn("items", entity_timeline_payload)
            self.assertIn("next_cursor", entity_timeline_payload)

            office_timeline_payload = asyncio.run(
                route_map["/api/inspect/office/timeline"].endpoint(limit=5, cursor=None)
            )
            self.assertIn("items", office_timeline_payload)
            self.assertIn("next_cursor", office_timeline_payload)

            integrity_latest_payload = asyncio.run(route_map["/api/integrity/latest"].endpoint())
            self.assertIn("report_hash", integrity_latest_payload)

            integrity_history_payload = asyncio.run(route_map["/api/integrity/history"].endpoint(limit=5, cursor=None))
            self.assertIn("items", integrity_history_payload)
            self.assertIn("next_cursor", integrity_history_payload)

            stability_runs_payload = asyncio.run(route_map["/api/stability/runs"].endpoint())
            self.assertIn("items", stability_runs_payload)
            self.assertGreaterEqual(stability_runs_payload["count"], 1)

            stability_run_payload = asyncio.run(route_map["/api/stability/run/{run_id}"].endpoint("run_test"))
            self.assertEqual(stability_run_payload.get("run_id"), "run_test")
            self.assertIn("checkpoints", stability_run_payload)

            health_payload = asyncio.run(route_map["/api/health"].endpoint())
            self.assertIn("last_snapshot_time", health_payload)
            self.assertIn("last_inspection_index_time", health_payload)
            self.assertIn("last_integrity_report_time", health_payload)

    def test_forbidden_imports_not_present(self) -> None:
        module_roots = [
            Path("appshak_integrity"),
            Path("appshak_inspection"),
            Path("appshak_observability"),
        ]
        forbidden_import_tokens = [
            "appshak_substrate",
            "sqlite3",
        ]
        for root in module_roots:
            for path in root.glob("*.py"):
                content = path.read_text(encoding="utf-8")
                for line in content.splitlines():
                    stripped = line.strip()
                    if not stripped.startswith("import ") and not stripped.startswith("from "):
                        continue
                    for token in forbidden_import_tokens:
                        self.assertNotIn(token, stripped, msg=f"{token} import found in {path}: {stripped}")


def _model_to_dict(model: object) -> dict:
    dump = getattr(model, "model_dump", None)
    if callable(dump):
        return dict(dump())
    as_dict = getattr(model, "dict", None)
    if callable(as_dict):
        return dict(as_dict())
    return dict(model)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
