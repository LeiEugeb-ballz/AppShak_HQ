from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from appshak_governance import (
    BOARDROOM_DECISION_THRESHOLD,
    STABILITY_ROLLING_WINDOW,
    AgentRegistry,
    AgentRegistryStore,
    BoardroomArbitrator,
    DeterministicReplayHarness,
    GovernanceEngine,
    RelationshipWeightEngine,
    TrustStabilityMetric,
    WaterCoolerPropagation,
)
from appshak_governance.utils import canonical_hash


def _agent_definitions():
    return [
        {"agent_id": "supervisor", "role": "supervisor", "authority_level": 1.0},
        {"agent_id": "command", "role": "command", "authority_level": 0.9},
        {"agent_id": "recon", "role": "recon", "authority_level": 0.7},
        {"agent_id": "forge", "role": "forge", "authority_level": 0.6},
    ]


def _projection_sequence():
    return [
        {
            "timestamp": "2026-03-01T00:00:01+00:00",
            "last_seen_event_id": 1,
            "current_event": {
                "type": "SUPERVISOR_START",
                "origin_id": "supervisor",
                "timestamp": "2026-03-01T00:00:01+00:00",
                "payload": {"agent_id": "supervisor"},
            },
            "tool_audit_counts": {"allowed": 0, "denied": 0},
            "derived": {"office_mode": "RUNNING", "stress_level": 0.3},
            "workers": {"supervisor": {"present": True, "state": "ACTIVE"}},
        },
        {
            "timestamp": "2026-03-01T00:00:02+00:00",
            "last_seen_event_id": 2,
            "current_event": {
                "type": "INTENT_DISPATCH",
                "origin_id": "supervisor",
                "timestamp": "2026-03-01T00:00:02+00:00",
                "payload": {"target_agent": "recon"},
            },
            "tool_audit_counts": {"allowed": 1, "denied": 0},
            "derived": {"office_mode": "RUNNING", "stress_level": 0.25},
            "workers": {
                "recon": {"present": True, "state": "ACTIVE"},
                "command": {"present": True, "state": "ACTIVE"},
            },
        },
        {
            "timestamp": "2026-03-01T00:00:03+00:00",
            "last_seen_event_id": 3,
            "current_event": {
                "type": "WORKER_HEARTBEAT_MISSED",
                "origin_id": "supervisor",
                "timestamp": "2026-03-01T00:00:03+00:00",
                "payload": {"agent_id": "forge"},
            },
            "tool_audit_counts": {"allowed": 1, "denied": 1},
            "derived": {"office_mode": "RUNNING", "stress_level": 0.5},
            "workers": {
                "forge": {"present": False, "state": "OFFLINE"},
                "recon": {"present": True, "state": "ACTIVE"},
            },
        },
        {
            "timestamp": "2026-03-01T00:00:04+00:00",
            "last_seen_event_id": 4,
            "current_event": {
                "type": "SUPERVISOR_STOP",
                "origin_id": "supervisor",
                "timestamp": "2026-03-01T00:00:04+00:00",
                "payload": {"agent_id": "supervisor"},
            },
            "tool_audit_counts": {"allowed": 1, "denied": 1},
            "derived": {"office_mode": "PAUSED", "stress_level": 0.1},
            "workers": {
                "recon": {"present": True, "state": "IDLE"},
                "command": {"present": True, "state": "IDLE"},
            },
        },
    ]


class TestGovernancePhaseThreeCompletion(unittest.TestCase):
    def test_agent_registry_atomic_persistence_and_replay_reproducible(self) -> None:
        with tempfile.TemporaryDirectory(prefix="governance_registry_") as tmp_dir:
            registry_path = Path(tmp_dir) / "registry" / "registry.json"
            ledger_path = Path(tmp_dir) / "ledger" / "audit.jsonl"
            engine = GovernanceEngine.from_agent_definitions(
                agent_definitions=_agent_definitions(),
                registry_path=registry_path,
                ledger_path=ledger_path,
            )
            previous_view = None
            for view in _projection_sequence():
                engine.ingest_projection_delta(previous_view=previous_view, current_view=view)
                previous_view = view

            persisted = AgentRegistryStore(registry_path).load()
            self.assertEqual(canonical_hash(persisted), canonical_hash(engine.registry.snapshot()))
            self.assertTrue(registry_path.exists())

            with tempfile.TemporaryDirectory(prefix="governance_registry_replay_") as replay_dir:
                replay_registry_path = Path(replay_dir) / "registry.json"
                replay_ledger_path = Path(replay_dir) / "audit.jsonl"
                replay = GovernanceEngine.from_agent_definitions(
                    agent_definitions=_agent_definitions(),
                    registry_path=replay_registry_path,
                    ledger_path=replay_ledger_path,
                )
                previous = None
                for view in _projection_sequence():
                    replay.ingest_projection_delta(previous_view=previous, current_view=view)
                    previous = view
                self.assertEqual(
                    canonical_hash(replay.registry.snapshot()),
                    canonical_hash(engine.registry.snapshot()),
                )

    def test_relationship_weight_engine_bounded_and_deterministic(self) -> None:
        registry_a = AgentRegistry.from_definitions(_agent_definitions())
        registry_b = AgentRegistry.from_definitions(_agent_definitions())
        outcomes = [
            {
                "agent_id": "recon",
                "outcome": "SUCCESS",
                "escalated": False,
                "source_event_type": "INTENT_DISPATCH",
                "source_event_id": 10,
                "source_timestamp": "2026-03-01T00:10:00+00:00",
            },
            {
                "agent_id": "recon",
                "outcome": "FAILURE",
                "escalated": True,
                "source_event_type": "PROPOSAL_INVALID",
                "source_event_id": 11,
                "source_timestamp": "2026-03-01T00:10:01+00:00",
            },
        ]

        engine = RelationshipWeightEngine()
        changes_a = engine.apply_outcomes(registry=registry_a, outcomes=outcomes)
        changes_b = engine.apply_outcomes(registry=registry_b, outcomes=outcomes)
        self.assertEqual([change.as_dict() for change in changes_a], [change.as_dict() for change in changes_b])
        self.assertEqual(canonical_hash(registry_a.snapshot()), canonical_hash(registry_b.snapshot()))

        snapshot = registry_a.snapshot()
        for agent_state in snapshot["agents"].values():
            self.assertGreaterEqual(agent_state["reputation_score"], 0.0)
            self.assertLessEqual(agent_state["reputation_score"], 1.0)
            for weight in agent_state["trust_weights"].values():
                self.assertGreaterEqual(weight, 0.0)
                self.assertLessEqual(weight, 1.0)

        self.assertLess(changes_a[1].reputation_delta, changes_a[0].reputation_delta)

    def test_boardroom_arbitration_deterministic_formula_and_threshold(self) -> None:
        registry = AgentRegistry.from_definitions(_agent_definitions())
        arbitrator = BoardroomArbitrator()
        ballots = [
            {"agent_id": "supervisor", "reasoning_score": 0.9},
            {"agent_id": "command", "reasoning_score": 1.2},
            {"agent_id": "recon", "reasoning_score": -0.3},
            {"agent_id": "forge", "reasoning_score": 0.6},
        ]

        result_1 = arbitrator.arbitrate(registry=registry, target_agent="command", ballots=ballots)
        result_2 = arbitrator.arbitrate(registry=registry, target_agent="command", ballots=ballots)
        self.assertEqual(result_1.as_dict(), result_2.as_dict())
        self.assertEqual(result_1.threshold, BOARDROOM_DECISION_THRESHOLD)
        self.assertEqual(result_1.approved, result_1.aggregate_score >= BOARDROOM_DECISION_THRESHOLD)
        for vote in result_1.votes:
            expected = vote.reasoning_score * vote.authority_level * vote.trust_weight
            self.assertAlmostEqual(vote.decision_score, expected, places=12)
            self.assertGreaterEqual(vote.reasoning_score, 0.0)
            self.assertLessEqual(vote.reasoning_score, 1.0)

    def test_water_cooler_propagation_deterministic_idle_trigger_and_metric(self) -> None:
        registry = AgentRegistry.from_definitions(_agent_definitions())
        water_cooler = WaterCoolerPropagation()
        previous_view = {
            "last_seen_event_id": 1,
            "derived": {"office_mode": "RUNNING", "stress_level": 0.7},
        }
        current_view = {
            "last_seen_event_id": 2,
            "derived": {"office_mode": "PAUSED", "stress_level": 0.1},
            "current_event": {
                "type": "SUPERVISOR_STOP",
                "origin_id": "supervisor",
                "timestamp": "2026-03-01T00:12:00+00:00",
                "payload": {"agent_id": "supervisor"},
            },
        }

        result = water_cooler.maybe_propagate(registry=registry, previous_view=previous_view, current_view=current_view)
        self.assertTrue(result["triggered"])
        lesson = result["lesson"]
        self.assertIsInstance(lesson, dict)
        self.assertIn("lesson_id", lesson)
        self.assertIn("recipients", lesson)
        self.assertGreater(result["propagation_metric"], 0.0)
        self.assertLessEqual(result["propagation_metric"], 1.0)

        second = water_cooler.maybe_propagate(registry=registry, previous_view=current_view, current_view=current_view)
        self.assertFalse(second["triggered"])

    def test_trust_stability_metric_rolling_window_fixed(self) -> None:
        registry = AgentRegistry.from_definitions(_agent_definitions())
        relationship = RelationshipWeightEngine()
        for index in range(10):
            relationship.apply_outcomes(
                registry=registry,
                outcomes=[
                    {
                        "agent_id": "recon",
                        "outcome": "SUCCESS" if index % 2 == 0 else "FAILURE",
                        "escalated": index % 3 == 0,
                        "source_event_type": "INTENT_DISPATCH",
                        "source_event_id": index + 1,
                        "source_timestamp": f"2026-03-01T00:20:{index:02d}+00:00",
                    }
                ],
            )

        metric = TrustStabilityMetric()
        result = metric.compute(registry=registry)
        self.assertEqual(result["window_size"], STABILITY_ROLLING_WINDOW)
        self.assertIn("per_agent_variance", result)
        self.assertIn("global_variance", result)
        self.assertGreaterEqual(result["global_variance"], 0.0)
        self.assertEqual(result["recorded_version"], registry.version)

    def test_governance_audit_ledger_reconstruction_and_hash_validation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="governance_ledger_") as tmp_dir:
            registry_path = Path(tmp_dir) / "registry.json"
            ledger_path = Path(tmp_dir) / "ledger.jsonl"
            engine = GovernanceEngine.from_agent_definitions(
                agent_definitions=_agent_definitions(),
                registry_path=registry_path,
                ledger_path=ledger_path,
            )

            previous_view = None
            for view in _projection_sequence():
                engine.ingest_projection_delta(previous_view=previous_view, current_view=view)
                previous_view = view

            chain_valid = engine.ledger.validate_hash_chain() if engine.ledger is not None else False
            reconstructed = engine.reconstruct_registry_from_ledger()
            self.assertTrue(chain_valid)
            self.assertEqual(canonical_hash(reconstructed), canonical_hash(engine.registry.snapshot()))
            self.assertTrue(engine.ledger.validate_registry_hash(registry_state=engine.registry.snapshot()))

    def test_deterministic_replay_harness_zero_tolerance(self) -> None:
        sequence = _projection_sequence()
        harness = DeterministicReplayHarness()
        with tempfile.TemporaryDirectory(prefix="governance_replay_a_") as dir_a:
            result_a = harness.run(
                agent_definitions=_agent_definitions(),
                projection_views=sequence,
                registry_path=Path(dir_a) / "registry.json",
                ledger_path=Path(dir_a) / "ledger.jsonl",
            )
        with tempfile.TemporaryDirectory(prefix="governance_replay_b_") as dir_b:
            result_b = harness.run(
                agent_definitions=_agent_definitions(),
                projection_views=sequence,
                registry_path=Path(dir_b) / "registry.json",
                ledger_path=Path(dir_b) / "ledger.jsonl",
            )

        self.assertTrue(result_a.chain_valid)
        self.assertTrue(result_b.chain_valid)
        self.assertTrue(result_a.hashes_equal)
        self.assertTrue(result_b.hashes_equal)
        self.assertEqual(result_a.final_registry_hash, result_b.final_registry_hash)
        self.assertEqual(result_a.reconstructed_registry_hash, result_b.reconstructed_registry_hash)

    def test_governance_module_has_no_runtime_coupling_imports(self) -> None:
        governance_files = list(Path("appshak_governance").glob("*.py"))
        banned_tokens = [
            "appshak_substrate",
            "sqlite3",
            "appshak.supervisor",
            "appshak_projection.projector",
        ]
        for file_path in governance_files:
            content = file_path.read_text(encoding="utf-8")
            for token in banned_tokens:
                self.assertNotIn(token, content, msg=f"{token} found in {file_path}")


if __name__ == "__main__":
    unittest.main()
