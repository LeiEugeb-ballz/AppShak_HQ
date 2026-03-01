from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

from .constants import (
    AUTHORITY_BANDS,
    RELATIONSHIP_ESCALATION_PENALTY,
    RELATIONSHIP_FAILURE_STEP,
    RELATIONSHIP_SUCCESS_STEP,
)
from .registry import AgentRegistry
from .utils import clamp, normalize_agent_id


@dataclass(frozen=True)
class TrustChange:
    subject_id: str
    outcome: str
    escalated: bool
    reputation_delta: float
    observer_trust_deltas: Dict[str, float]
    source_event_type: str
    source_event_id: int
    source_timestamp: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "subject_id": self.subject_id,
            "outcome": self.outcome,
            "escalated": self.escalated,
            "reputation_delta": self.reputation_delta,
            "observer_trust_deltas": dict(self.observer_trust_deltas),
            "source_event_type": self.source_event_type,
            "source_event_id": self.source_event_id,
            "source_timestamp": self.source_timestamp,
        }


class RelationshipWeightEngine:
    def __init__(
        self,
        *,
        success_step: float = RELATIONSHIP_SUCCESS_STEP,
        failure_step: float = RELATIONSHIP_FAILURE_STEP,
        escalation_penalty: float = RELATIONSHIP_ESCALATION_PENALTY,
    ) -> None:
        self._success_step = max(0.0, float(success_step))
        self._failure_step = max(0.0, float(failure_step))
        self._escalation_penalty = max(0.0, float(escalation_penalty))

    def apply_outcomes(
        self,
        *,
        registry: AgentRegistry,
        outcomes: Iterable[Dict[str, object]],
    ) -> List[TrustChange]:
        changes: List[TrustChange] = []
        for outcome in outcomes:
            subject_id = normalize_agent_id(outcome.get("agent_id"))
            if not subject_id or not registry.has_agent(subject_id):
                continue

            outcome_type = str(outcome.get("outcome", "FAILURE")).strip().upper()
            escalated = bool(outcome.get("escalated", False))
            event_type = str(outcome.get("source_event_type", "UNKNOWN")).strip().upper() or "UNKNOWN"
            event_id = int(outcome.get("source_event_id", 0))
            source_timestamp = str(outcome.get("source_timestamp", ""))

            reputation_delta = self._compute_reputation_delta(
                outcome_type=outcome_type,
                escalated=escalated,
                subject_authority=registry.authority_level(subject_id),
            )
            observer_trust_deltas: Dict[str, float] = {}
            for observer_id in registry.agent_ids:
                observer_scale = self._authority_scale(registry.authority_level(observer_id))
                observer_trust_deltas[observer_id] = reputation_delta * observer_scale

            registry.apply_outcome_update(
                subject_id=subject_id,
                reputation_delta=reputation_delta,
                observer_trust_deltas=observer_trust_deltas,
                updated_at=source_timestamp,
            )
            changes.append(
                TrustChange(
                    subject_id=subject_id,
                    outcome=outcome_type,
                    escalated=escalated,
                    reputation_delta=reputation_delta,
                    observer_trust_deltas=observer_trust_deltas,
                    source_event_type=event_type,
                    source_event_id=event_id,
                    source_timestamp=source_timestamp,
                )
            )
        return changes

    def _compute_reputation_delta(self, *, outcome_type: str, escalated: bool, subject_authority: float) -> float:
        authority_scale = self._authority_scale(subject_authority)
        if outcome_type == "SUCCESS":
            return self._success_step * authority_scale
        penalty = self._failure_step
        if escalated:
            penalty += self._escalation_penalty
        return -penalty * authority_scale

    @staticmethod
    def _authority_scale(authority_level: float) -> float:
        normalized = clamp(float(authority_level), 0.0, 1.0)
        if normalized >= 0.8:
            return AUTHORITY_BANDS["HIGH"]
        if normalized >= 0.5:
            return AUTHORITY_BANDS["MEDIUM"]
        return AUTHORITY_BANDS["LOW"]
