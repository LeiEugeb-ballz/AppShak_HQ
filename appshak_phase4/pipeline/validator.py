from __future__ import annotations

from datetime import timezone
from typing import Any, Dict, List

from appshak_inspection.utils import parse_iso

from appshak_phase4.contracts import IntegrityRecord, InspectionRecord, Phase4Snapshot, ValidationResult


class SnapshotValidator:
    def __init__(self, *, stall_threshold_seconds: int = 300) -> None:
        self._stall_threshold_seconds = max(1, int(stall_threshold_seconds))

    def validate(self, snapshot: Phase4Snapshot) -> ValidationResult:
        anomalies: List[Dict[str, Any]] = []

        if not snapshot.agents:
            anomalies.append(
                {
                    "code": "missing_agents",
                    "severity": "high",
                    "message": "No agents present in projection snapshot.",
                    "agent_id": "",
                }
            )

        anomalies.extend(self._stalled_state_anomalies(snapshot))
        anomalies.extend(self._invalid_transition_anomalies(snapshot))

        if not snapshot.events:
            anomalies.append(
                {
                    "code": "empty_event_stream",
                    "severity": "high",
                    "message": "No events found in normalized projection snapshot.",
                    "agent_id": "",
                }
            )

        coverage = self._build_coverage(snapshot, anomalies)
        inspection = InspectionRecord(
            run_id=snapshot.run_id,
            timestamp=snapshot.timestamp,
            anomalies=anomalies,
            coverage=coverage,
        )

        integrity = IntegrityRecord(
            run_id=snapshot.run_id,
            timestamp=snapshot.timestamp,
            consistency_score=self._consistency_score(anomalies),
            violations=self._violations_from_anomalies(anomalies),
        )

        return ValidationResult(snapshot=snapshot, inspection=inspection, integrity=integrity)

    def _stalled_state_anomalies(self, snapshot: Phase4Snapshot) -> List[Dict[str, Any]]:
        anomalies: List[Dict[str, Any]] = []
        snapshot_time = parse_iso(snapshot.timestamp)
        if snapshot_time is None:
            return anomalies
        snapshot_time = snapshot_time.astimezone(timezone.utc)

        for agent in snapshot.agents:
            state = str(agent.get("state", "")).strip().upper()
            if state not in {"ACTIVE", "RESTARTING"}:
                continue
            last_event_at = parse_iso(agent.get("last_event_at"))
            if last_event_at is None:
                anomalies.append(
                    {
                        "code": "stalled_state",
                        "severity": "medium",
                        "message": "Active state without last_event_at timestamp.",
                        "agent_id": str(agent.get("agent_id", "")),
                        "state": state,
                    }
                )
                continue
            age_seconds = int((snapshot_time - last_event_at.astimezone(timezone.utc)).total_seconds())
            if age_seconds > self._stall_threshold_seconds:
                anomalies.append(
                    {
                        "code": "stalled_state",
                        "severity": "medium",
                        "message": "State appears stalled beyond threshold.",
                        "agent_id": str(agent.get("agent_id", "")),
                        "state": state,
                        "age_seconds": max(0, age_seconds),
                        "threshold_seconds": self._stall_threshold_seconds,
                    }
                )
        return anomalies

    def _invalid_transition_anomalies(self, snapshot: Phase4Snapshot) -> List[Dict[str, Any]]:
        anomalies: List[Dict[str, Any]] = []
        last_seen_event_id = _as_int(snapshot.metrics.get("last_seen_event_id"), default=0)

        for agent in snapshot.agents:
            state = str(agent.get("state", "")).strip().upper()
            present = bool(agent.get("present", False))
            agent_id = str(agent.get("agent_id", ""))
            agent_last_seen_event = _as_int(agent.get("last_seen_event_id"), default=0)

            if state in {"ACTIVE", "RESTARTING"} and not present:
                anomalies.append(
                    {
                        "code": "invalid_transition",
                        "severity": "high",
                        "message": "Agent marked active/restarting while not present.",
                        "agent_id": agent_id,
                        "state": state,
                        "present": present,
                    }
                )
            if state == "OFFLINE" and present:
                anomalies.append(
                    {
                        "code": "invalid_transition",
                        "severity": "medium",
                        "message": "Agent marked offline while present.",
                        "agent_id": agent_id,
                        "state": state,
                        "present": present,
                    }
                )
            if agent_last_seen_event > last_seen_event_id:
                anomalies.append(
                    {
                        "code": "invalid_transition",
                        "severity": "high",
                        "message": "Agent event cursor exceeds snapshot event cursor.",
                        "agent_id": agent_id,
                        "agent_last_seen_event_id": agent_last_seen_event,
                        "snapshot_last_seen_event_id": last_seen_event_id,
                    }
                )

        return anomalies

    def _build_coverage(self, snapshot: Phase4Snapshot, anomalies: List[Dict[str, Any]]) -> Dict[str, Any]:
        active_agents = 0
        present_agents = 0
        for agent in snapshot.agents:
            if bool(agent.get("present", False)):
                present_agents += 1
            if str(agent.get("state", "")).strip().upper() in {"ACTIVE", "RESTARTING"}:
                active_agents += 1

        return {
            "agent_count": len(snapshot.agents),
            "present_agent_count": present_agents,
            "active_agent_count": active_agents,
            "event_count": len(snapshot.events),
            "events_processed": _as_int(snapshot.metrics.get("events_processed"), default=0),
            "event_queue_size": _as_int(snapshot.metrics.get("event_queue_size"), default=0),
            "anomaly_count": len(anomalies),
            "high_severity_anomalies": len(
                [anomaly for anomaly in anomalies if str(anomaly.get("severity", "")).lower() == "high"]
            ),
        }

    def _consistency_score(self, anomalies: List[Dict[str, Any]]) -> float:
        if not anomalies:
            return 1.0

        penalty = 0.0
        for anomaly in anomalies:
            severity = str(anomaly.get("severity", "")).strip().lower()
            if severity == "high":
                penalty += 0.2
            elif severity == "medium":
                penalty += 0.1
            else:
                penalty += 0.05
        score = max(0.0, 1.0 - penalty)
        return round(score, 6)

    def _violations_from_anomalies(self, anomalies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        violations: List[Dict[str, Any]] = []
        for anomaly in anomalies:
            violations.append(
                {
                    "code": str(anomaly.get("code", "")),
                    "severity": str(anomaly.get("severity", "")),
                    "message": str(anomaly.get("message", "")),
                    "agent_id": str(anomaly.get("agent_id", "")),
                }
            )
        return violations


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default
