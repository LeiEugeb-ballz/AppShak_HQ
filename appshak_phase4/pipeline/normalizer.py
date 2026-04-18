from __future__ import annotations

from typing import Any, Dict, Mapping

from appshak_integrity.utils import canonical_hash

from appshak_phase4.adapters import projection_to_phase4_snapshot
from appshak_phase4.contracts import Phase4Snapshot


class SnapshotNormalizer:
    def normalize(self, snapshot: Phase4Snapshot | Mapping[str, Any]) -> Phase4Snapshot:
        if isinstance(snapshot, Phase4Snapshot):
            source = snapshot
        else:
            source = projection_to_phase4_snapshot(snapshot)

        timestamp = str(source.timestamp)
        normalized_agents = self._normalize_agents(source.agents, timestamp=timestamp)
        normalized_events = self._normalize_events(source.events, timestamp=timestamp)
        normalized_metrics = self._normalize_metrics(source.metrics)

        return Phase4Snapshot(
            run_id=str(source.run_id),
            timestamp=timestamp,
            agents=normalized_agents,
            events=normalized_events,
            metrics=normalized_metrics,
        )

    def _normalize_agents(self, agents: list[Dict[str, Any]], *, timestamp: str) -> list[Dict[str, Any]]:
        normalized: list[Dict[str, Any]] = []
        for agent in agents:
            if not isinstance(agent, Mapping):
                continue
            agent_id = str(agent.get("agent_id", "")).strip().lower()
            if not agent_id:
                continue
            normalized.append(
                {
                    "agent_id": agent_id,
                    "present": bool(agent.get("present", False)),
                    "state": str(agent.get("state", "IDLE")).strip().upper() or "IDLE",
                    "last_event_type": str(agent.get("last_event_type", "")).strip().upper(),
                    "last_event_at": str(agent.get("last_event_at", "")).strip() or timestamp,
                    "restart_count": _as_int(agent.get("restart_count"), default=0),
                    "missed_heartbeat_count": _as_int(agent.get("missed_heartbeat_count"), default=0),
                    "last_seen_event_id": _as_int(agent.get("last_seen_event_id"), default=0),
                }
            )
        normalized.sort(key=lambda row: row["agent_id"])
        return normalized

    def _normalize_events(self, events: list[Dict[str, Any]], *, timestamp: str) -> list[Dict[str, Any]]:
        normalized: list[Dict[str, Any]] = []
        for event in events:
            if not isinstance(event, Mapping):
                continue
            payload_raw = event.get("payload")
            payload = dict(payload_raw) if isinstance(payload_raw, Mapping) else {}
            event_type = str(event.get("type", "")).strip().upper()
            if not event_type:
                continue
            normalized.append(
                {
                    "event_id": _as_int(event.get("event_id"), default=0),
                    "type": event_type,
                    "timestamp": str(event.get("timestamp", "")).strip() or timestamp,
                    "origin_id": str(event.get("origin_id", "")).strip(),
                    "payload": payload,
                }
            )
        normalized.sort(key=self._event_sort_key)
        return normalized

    def _normalize_metrics(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        source = metrics if isinstance(metrics, Mapping) else {}
        tool_audit_counts_raw = source.get("tool_audit_counts")
        event_type_counts_raw = source.get("event_type_counts")
        derived_raw = source.get("derived")

        tool_audit_counts = (
            dict(tool_audit_counts_raw)
            if isinstance(tool_audit_counts_raw, Mapping)
            else {"allowed": 0, "denied": 0}
        )
        event_type_counts = dict(event_type_counts_raw) if isinstance(event_type_counts_raw, Mapping) else {}
        derived = dict(derived_raw) if isinstance(derived_raw, Mapping) else {}

        return {
            "running": bool(source.get("running", False)),
            "event_queue_size": _as_int(source.get("event_queue_size"), default=0),
            "events_processed": _as_int(source.get("events_processed"), default=0),
            "last_seen_event_id": _as_int(source.get("last_seen_event_id"), default=0),
            "last_seen_tool_audit_id": _as_int(source.get("last_seen_tool_audit_id"), default=0),
            "tool_audit_counts": {
                "allowed": _as_int(tool_audit_counts.get("allowed"), default=0),
                "denied": _as_int(tool_audit_counts.get("denied"), default=0),
            },
            "event_type_counts": {
                str(key).strip().upper(): _as_int(value, default=0)
                for key, value in sorted(event_type_counts.items(), key=lambda row: str(row[0]).upper())
                if str(key).strip()
            },
            "derived": derived,
        }

    def _event_sort_key(self, event: Mapping[str, Any]) -> tuple[int, str, str, str]:
        return (
            _as_int(event.get("event_id"), default=0),
            str(event.get("timestamp", "")),
            str(event.get("type", "")),
            canonical_hash(event.get("payload", {})),
        )


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default
