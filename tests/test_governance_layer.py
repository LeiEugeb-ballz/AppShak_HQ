from __future__ import annotations

import unittest

from appshak_governance import (
    AgentRegistry,
    BoardroomArbitrator,
    GovernanceFormalizationLayer,
)


def _agent_configs():
    return [
        {"agent_id": "supervisor", "role": "supervisor", "authority_level": 1.0},
        {"agent_id": "command", "role": "command", "authority_level": 0.9},
        {"agent_id": "recon", "role": "recon", "authority_level": 0.75},
        {"agent_id": "forge", "role": "forge", "authority_level": 0.7},
    ]


def _projection_steps():
    return [
        {
            "last_seen_event_id": 1,
            "current_event": {
                "type": "INTENT_DISPATCH",
                "origin_id": "supervisor",
                "payload": {"target_agent": "recon"},
            },
            "tool_audit_counts": {"allowed": 0, "denied": 0},
            "workers": {
                "recon": {"present": True, "state": "ACTIVE"},
                "command": {"present": True, "state": "ACTIVE"},
            },
        },
        {
            "last_seen_event_id": 2,
            "current_event": {
                "type": "WORKER_RESTART_SCHEDULED",
                "origin_id": "supervisor",
                "payload": {"agent_id": "forge"},
            },
            "tool_audit_counts": {"allowed": 1, "denied": 0},
            "workers": {
                "forge": {"present": True, "state": "RESTARTING"},
                "recon": {"present": True, "state": "ACTIVE"},
            },
        },
        {
            "last_seen_event_id": 3,
            "current_event": {
                "type": "WORKER_RESTARTED",
                "origin_id": "supervisor",
                "payload": {"agent_id": "forge"},
            },
            "tool_audit_counts": {"allowed": 1, "denied": 1},
            "workers": {
                "forge": {"present": True, "state": "ACTIVE"},
                "command": {"present": True, "state": "ACTIVE"},
            },
        },
        {
            "last_seen_event_id": 4,
            "current_event": {
                "type": "PROPOSAL_INVALID",
                "origin_id": "supervisor",
                "payload": {"worker": "command"},
            },
            "tool_audit_counts": {"allowed": 2, "denied": 1},
            "workers": {
                "command": {"present": True, "state": "ACTIVE"},
            },
        },
    ]


class TestGovernanceFormalizationLayer(unittest.TestCase):
    def test_identical_event_sequence_has_identical_trust_evolution(self) -> None:
        engine_a = GovernanceFormalizationLayer(registry=AgentRegistry(_agent_configs()))
        engine_b = GovernanceFormalizationLayer(registry=AgentRegistry(_agent_configs()))

        previous_view_a = {"last_seen_event_id": 0, "tool_audit_counts": {"allowed": 0, "denied": 0}}
        previous_view_b = {"last_seen_event_id": 0, "tool_audit_counts": {"allowed": 0, "denied": 0}}
        steps = _projection_steps()

        history_a = []
        history_b = []
        for step in steps:
            result_a = engine_a.ingest_projection_delta(previous_view=previous_view_a, current_view=step)
            result_b = engine_b.ingest_projection_delta(previous_view=previous_view_b, current_view=step)
            history_a.append(result_a["registry"])
            history_b.append(result_b["registry"])
            previous_view_a = step
            previous_view_b = step

        self.assertEqual(history_a, history_b)
        self.assertEqual(engine_a.registry.to_dict(), engine_b.registry.to_dict())

    def test_identical_arbitration_inputs_have_identical_outputs(self) -> None:
        layer = GovernanceFormalizationLayer(registry=AgentRegistry(_agent_configs()))
        previous_view = {"last_seen_event_id": 0, "tool_audit_counts": {"allowed": 0, "denied": 0}}

        for step in _projection_steps():
            layer.ingest_projection_delta(previous_view=previous_view, current_view=step)
            previous_view = step

        arbitrator = BoardroomArbitrator()
        ballots = [
            {"agent_id": "supervisor", "reasoning_score": 0.9},
            {"agent_id": "command", "reasoning_score": 0.8},
            {"agent_id": "recon", "reasoning_score": 0.7},
            {"agent_id": "forge", "reasoning_score": 0.6},
        ]

        result_1 = arbitrator.arbitrate(
            registry=layer.registry,
            target_agent="command",
            ballots=ballots,
            threshold=0.35,
        )
        result_2 = arbitrator.arbitrate(
            registry=layer.registry,
            target_agent="command",
            ballots=ballots,
            threshold=0.35,
        )

        self.assertEqual(result_1, result_2)
        self.assertEqual(result_1["approved"], result_1["aggregate_score"] >= result_1["threshold"])
        for vote in result_1["votes"]:
            expected = vote["reasoning_score"] * vote["authority_level"] * vote["trust_weight"]
            self.assertAlmostEqual(vote["decision_score"], expected, places=12)

    def test_trust_stability_metric_uses_registry_history(self) -> None:
        layer = GovernanceFormalizationLayer(registry=AgentRegistry(_agent_configs()))
        previous_view = {"last_seen_event_id": 0, "tool_audit_counts": {"allowed": 0, "denied": 0}}
        last_result = None

        for step in _projection_steps():
            last_result = layer.ingest_projection_delta(previous_view=previous_view, current_view=step)
            previous_view = step

        self.assertIsNotNone(last_result)
        stability = last_result["stability"]
        self.assertIn("per_agent_variance", stability)
        self.assertIn("global_variance", stability)
        self.assertIn("sample_count", stability)
        self.assertGreaterEqual(stability["global_variance"], 0.0)
        self.assertEqual(stability["sample_count"], layer.registry.version)


if __name__ == "__main__":
    unittest.main()
