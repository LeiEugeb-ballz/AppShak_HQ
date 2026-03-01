from __future__ import annotations

from typing import Dict, List, Mapping, Sequence

from .constants import (
    ESCALATION_EVENT_TYPES,
    FAILURE_EVENT_TYPES,
    SUCCESS_EVENT_TYPES,
    WORKER_STATE_ESCALATED,
)
from .utils import as_int, normalize_agent_id


class ProjectionOutcomeAdapter:
    def derive_outcomes(
        self,
        *,
        previous_view: Mapping[str, object] | None,
        current_view: Mapping[str, object] | None,
        known_agents: Sequence[str],
    ) -> List[Dict[str, object]]:
        previous = previous_view if isinstance(previous_view, Mapping) else {}
        current = current_view if isinstance(current_view, Mapping) else {}
        known = {normalize_agent_id(agent_id) for agent_id in known_agents if normalize_agent_id(agent_id)}
        outcomes: List[Dict[str, object]] = []

        prev_event_id = as_int(previous.get("last_seen_event_id"), default=0)
        curr_event_id = as_int(current.get("last_seen_event_id"), default=0)
        if curr_event_id > prev_event_id:
            current_event = current.get("current_event")
            if isinstance(current_event, Mapping):
                event_type = str(current_event.get("type", "")).strip().upper()
                timestamp = str(current_event.get("timestamp", "")).strip()
                subject_id = self._resolve_subject_id(current_event=current_event, known_agents=known)
                if event_type and subject_id:
                    outcome = self._event_outcome(event_type)
                    if outcome:
                        outcomes.append(
                            {
                                "agent_id": subject_id,
                                "outcome": outcome,
                                "escalated": event_type in ESCALATION_EVENT_TYPES,
                                "source_event_type": event_type,
                                "source_event_id": curr_event_id,
                                "source_timestamp": timestamp,
                            }
                        )

        prev_allowed, prev_denied = self._tool_counts(previous)
        curr_allowed, curr_denied = self._tool_counts(current)
        allowed_delta = max(0, curr_allowed - prev_allowed)
        denied_delta = max(0, curr_denied - prev_denied)
        active_agents = self._active_agents(current, known)
        for agent_id in active_agents:
            if allowed_delta > 0:
                outcomes.append(
                    {
                        "agent_id": agent_id,
                        "outcome": "SUCCESS",
                        "escalated": False,
                        "source_event_type": "TOOL_AUDIT_ALLOWED_DELTA",
                        "source_event_id": curr_event_id,
                        "source_timestamp": str(current.get("timestamp", "")),
                    }
                )
            if denied_delta > 0:
                outcomes.append(
                    {
                        "agent_id": agent_id,
                        "outcome": "FAILURE",
                        "escalated": True,
                        "source_event_type": "TOOL_AUDIT_DENIED_DELTA",
                        "source_event_id": curr_event_id,
                        "source_timestamp": str(current.get("timestamp", "")),
                    }
                )
        return outcomes

    @staticmethod
    def _resolve_subject_id(*, current_event: Mapping[str, object], known_agents: set[str]) -> str:
        payload = current_event.get("payload")
        if isinstance(payload, Mapping):
            for key in ("target_agent", "agent_id", "worker"):
                candidate = normalize_agent_id(payload.get(key))
                if candidate and candidate in known_agents:
                    return candidate

        origin_id = normalize_agent_id(current_event.get("origin_id"))
        if origin_id and origin_id in known_agents:
            return origin_id
        return ""

    @staticmethod
    def _event_outcome(event_type: str) -> str:
        if event_type in SUCCESS_EVENT_TYPES:
            return "SUCCESS"
        if event_type in FAILURE_EVENT_TYPES:
            return "FAILURE"
        return ""

    @staticmethod
    def _tool_counts(view: Mapping[str, object]) -> tuple[int, int]:
        counts = view.get("tool_audit_counts")
        if not isinstance(counts, Mapping):
            return (0, 0)
        return (
            max(0, as_int(counts.get("allowed"), default=0)),
            max(0, as_int(counts.get("denied"), default=0)),
        )

    @staticmethod
    def _active_agents(view: Mapping[str, object], known_agents: set[str]) -> List[str]:
        workers = view.get("workers")
        if not isinstance(workers, Mapping):
            return sorted(known_agents)
        active: List[str] = []
        for worker_id_raw, state_raw in workers.items():
            worker_id = normalize_agent_id(worker_id_raw)
            if not worker_id or worker_id not in known_agents:
                continue
            if not isinstance(state_raw, Mapping):
                continue
            present = bool(state_raw.get("present", False))
            state = str(state_raw.get("state", "")).strip().upper()
            if present or state in {"ACTIVE", "IDLE"} or state in WORKER_STATE_ESCALATED:
                active.append(worker_id)
        if not active:
            return sorted(known_agents)
        active.sort()
        return active
