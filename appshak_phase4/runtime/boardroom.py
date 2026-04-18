from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping

from appshak_governance import BOARDROOM_DECISION_THRESHOLD, AgentRegistry, AgentRegistryStore, BoardroomArbitrator, GovernanceAuditLedger


class BoardroomExecutionLayer:
    def __init__(
        self,
        *,
        registry_path: str | Path = "appshak_state/governance/registry.json",
        ledger_path: str | Path = "appshak_state/governance/ledger.jsonl",
        chief_override_threshold: float = 0.30,
        chief_override_margin: float = 0.05,
    ) -> None:
        self.registry_path = Path(registry_path)
        self.ledger_path = Path(ledger_path)
        self.arbitrator = BoardroomArbitrator()
        self.chief_override_threshold = max(0.0, min(1.0, float(chief_override_threshold)))
        self.chief_override_margin = max(0.0, min(1.0, float(chief_override_margin)))

    def execute(
        self,
        *,
        proposal: Mapping[str, Any],
        snapshot: Mapping[str, Any],
        cycle_id: str,
    ) -> Dict[str, Any]:
        registry = self._resolve_registry(snapshot)
        ballots = self._build_ballots(snapshot=snapshot, proposal=proposal)
        target_agent = str(proposal.get("target_agent", "forge")).strip().lower() or "forge"
        arbitration = self.arbitrator.arbitrate(
            registry=registry,
            target_agent=target_agent,
            ballots=ballots,
        ).as_dict()

        chief_vote = self._chief_vote(arbitration.get("votes", []))
        approved_from_votes = bool(arbitration.get("approved", False))
        aggregate_score = _as_float(arbitration.get("aggregate_score"), default=0.0)
        threshold = _as_float(arbitration.get("threshold"), default=BOARDROOM_DECISION_THRESHOLD)
        chief_override = (
            not approved_from_votes
            and chief_vote.get("decision_score", 0.0) >= self.chief_override_threshold
            and aggregate_score >= max(0.0, threshold - self.chief_override_margin)
        )
        approved = approved_from_votes or chief_override

        return {
            "cycle_id": str(cycle_id),
            "proposal_id": str(proposal.get("proposal_id", "")),
            "proposal": dict(proposal),
            "votes": list(arbitration.get("votes", [])),
            "decision": {
                "approved": bool(approved),
                "approved_from_votes": bool(approved_from_votes),
                "chief_override": bool(chief_override),
                "chief_override_threshold": self.chief_override_threshold,
                "aggregate_score": aggregate_score,
                "threshold": threshold,
                "target_agent": target_agent,
            },
        }

    def _resolve_registry(self, snapshot: Mapping[str, Any]) -> AgentRegistry:
        registry_store = AgentRegistryStore(self.registry_path)
        if self.registry_path.exists():
            loaded = registry_store.load()
            if loaded.get("agents"):
                return AgentRegistry(loaded)

        definitions = self._agent_definitions(snapshot)
        fallback = AgentRegistry.from_definitions(definitions).snapshot()
        if self.ledger_path.exists():
            reconstructed = GovernanceAuditLedger(self.ledger_path).reconstruct_registry(fallback_registry=fallback)
            return AgentRegistry(reconstructed)
        return AgentRegistry(fallback)

    def _agent_definitions(self, snapshot: Mapping[str, Any]) -> List[Dict[str, Any]]:
        workers = snapshot.get("workers")
        worker_ids = (
            sorted([str(worker_id).strip().lower() for worker_id in workers.keys() if str(worker_id).strip()])
            if isinstance(workers, Mapping)
            else []
        )
        required = ["recon", "forge", "command"]
        for item in required:
            if item not in worker_ids:
                worker_ids.append(item)
        worker_ids = sorted(set(worker_ids))

        definitions: List[Dict[str, Any]] = []
        for agent_id in worker_ids:
            role = "worker"
            authority = 0.6
            if agent_id == "command":
                role = "chief"
                authority = 0.9
            elif agent_id == "recon":
                role = "scout"
                authority = 0.7
            elif agent_id == "forge":
                role = "builder"
                authority = 0.8
            definitions.append(
                {
                    "agent_id": agent_id,
                    "role": role,
                    "authority_level": authority,
                }
            )
        return definitions

    def _build_ballots(self, *, snapshot: Mapping[str, Any], proposal: Mapping[str, Any]) -> List[Dict[str, Any]]:
        queue_size = _as_int(snapshot.get("event_queue_size"), default=0)
        events_processed = _as_int(snapshot.get("events_processed"), default=0)
        running = bool(snapshot.get("running", False))
        derived = snapshot.get("derived")
        stress = _as_float(derived.get("stress_level"), default=0.0) if isinstance(derived, Mapping) else 0.0
        idle_triggered = bool(proposal.get("idle_triggered", False))

        scout_reasoning = _clamp01((1.0 - stress) + (0.08 if idle_triggered else -0.05))
        chief_reasoning = _clamp01(0.58 + (0.17 if running else -0.17) - min(queue_size, 10) * 0.02)
        builder_reasoning = _clamp01(0.45 + min(events_processed, 200) * 0.001 - min(queue_size, 10) * 0.01)

        return [
            {"agent_id": "recon", "reasoning_score": scout_reasoning},
            {"agent_id": "command", "reasoning_score": chief_reasoning},
            {"agent_id": "forge", "reasoning_score": builder_reasoning},
        ]

    def _chief_vote(self, votes: Any) -> Dict[str, Any]:
        if not isinstance(votes, list):
            return {"agent_id": "command", "decision_score": 0.0}
        for vote in votes:
            if not isinstance(vote, Mapping):
                continue
            if str(vote.get("agent_id", "")).strip().lower() == "command":
                return {
                    "agent_id": "command",
                    "decision_score": _as_float(vote.get("decision_score"), default=0.0),
                }
        return {"agent_id": "command", "decision_score": 0.0}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _as_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default
