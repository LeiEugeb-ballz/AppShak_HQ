from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping

REGISTRY_SCHEMA_VERSION = 1
REGISTRY_INITIAL_VERSION = 1
REGISTRY_EPOCH_TIMESTAMP = "1970-01-01T00:00:00+00:00"

TRUST_MIN = 0.0
TRUST_MAX = 1.0
REPUTATION_MIN = 0.0
REPUTATION_MAX = 1.0

RELATIONSHIP_SUCCESS_STEP = 0.05
RELATIONSHIP_FAILURE_STEP = 0.07
RELATIONSHIP_ESCALATION_PENALTY = 0.12

AUTHORITY_BANDS: Mapping[str, float] = {
    "HIGH": 1.2,
    "MEDIUM": 1.0,
    "LOW": 0.8,
}

BOARDROOM_REASONING_MIN = 0.0
BOARDROOM_REASONING_MAX = 1.0
BOARDROOM_DECISION_THRESHOLD = 0.35

WATER_COOLER_IDLE_STRESS_MAX = 0.2
WATER_COOLER_MAX_RECIPIENTS = 3

STABILITY_ROLLING_WINDOW = 5

SUCCESS_EVENT_TYPES = {
    "SUPERVISOR_START",
    "INTENT_DISPATCH",
    "WORKER_STARTED",
    "WORKER_RESTARTED",
}

FAILURE_EVENT_TYPES = {
    "SUPERVISOR_STOP",
    "PROPOSAL_INVALID",
    "WORKER_EXITED",
    "WORKER_HEARTBEAT_MISSED",
    "WORKER_RESTART_SCHEDULED",
}

ESCALATION_EVENT_TYPES = {
    "PROPOSAL_INVALID",
    "WORKER_EXITED",
    "WORKER_HEARTBEAT_MISSED",
}

WORKER_STATE_ESCALATED = {"OFFLINE", "RESTARTING"}


@dataclass(frozen=True)
class GovernanceOutcome:
    agent_id: str
    outcome: str
    escalated: bool
    source_event_type: str
    source_event_id: int
    source_timestamp: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "agent_id": self.agent_id,
            "outcome": self.outcome,
            "escalated": self.escalated,
            "source_event_type": self.source_event_type,
            "source_event_id": self.source_event_id,
            "source_timestamp": self.source_timestamp,
        }
