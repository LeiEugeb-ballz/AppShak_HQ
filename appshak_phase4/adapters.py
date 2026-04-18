from __future__ import annotations

from typing import Any, Dict, Mapping

from appshak_integrity.utils import canonical_hash
from appshak_projection.schemas import normalize_projection_view

from .contracts import Phase4Snapshot


def projection_to_phase4_snapshot(projection_snapshot: Mapping[str, Any]) -> Phase4Snapshot:
    normalized_projection = normalize_projection_view(projection_snapshot)
    timestamp = str(normalized_projection.get("timestamp", ""))
    run_id = _derive_run_id(normalized_projection)
    agents = _adapt_agents(normalized_projection)
    events = _adapt_events(normalized_projection)
    metrics = _adapt_metrics(normalized_projection)

    return Phase4Snapshot(
        run_id=run_id,
        timestamp=timestamp,
        agents=agents,
        events=events,
        metrics=metrics,
    )


def phase4_to_projection_snapshot(snapshot: Phase4Snapshot) -> Dict[str, Any]:
    workers: Dict[str, Dict[str, Any]] = {}
    for agent in snapshot.agents:
        agent_id = str(agent.get("agent_id", "")).strip().lower()
        if not agent_id:
            continue
        workers[agent_id] = {
            "present": bool(agent.get("present", False)),
            "state": str(agent.get("state", "IDLE")),
            "last_event_type": str(agent.get("last_event_type", "")).upper() or None,
            "last_event_at": str(agent.get("last_event_at", "")) or None,
            "restart_count": _as_int(agent.get("restart_count"), default=0),
            "missed_heartbeat_count": _as_int(agent.get("missed_heartbeat_count"), default=0),
            "last_seen_event_id": _as_int(agent.get("last_seen_event_id"), default=0),
        }

    current_event = None
    event_rows = [event for event in snapshot.events if isinstance(event, dict)]
    if event_rows:
        primary = event_rows[0]
        current_event = {
            "type": str(primary.get("type", "")).upper() or None,
            "timestamp": str(primary.get("timestamp", "")) or snapshot.timestamp,
            "origin_id": str(primary.get("origin_id", "")) or None,
            "payload": dict(primary.get("payload", {})) if isinstance(primary.get("payload"), Mapping) else {},
        }

    tool_audit_counts_raw = snapshot.metrics.get("tool_audit_counts")
    tool_audit_counts = (
        dict(tool_audit_counts_raw)
        if isinstance(tool_audit_counts_raw, Mapping)
        else {"allowed": 0, "denied": 0}
    )
    event_type_counts_raw = snapshot.metrics.get("event_type_counts")
    event_type_counts = dict(event_type_counts_raw) if isinstance(event_type_counts_raw, Mapping) else {}
    derived_raw = snapshot.metrics.get("derived")
    derived = dict(derived_raw) if isinstance(derived_raw, Mapping) else {}

    return normalize_projection_view(
        {
            "schema_version": 1,
            "timestamp": snapshot.timestamp,
            "last_updated_at": snapshot.timestamp,
            "last_seen_event_id": _as_int(snapshot.metrics.get("last_seen_event_id"), default=0),
            "last_seen_tool_audit_id": _as_int(snapshot.metrics.get("last_seen_tool_audit_id"), default=0),
            "running": bool(snapshot.metrics.get("running", False)),
            "event_queue_size": _as_int(snapshot.metrics.get("event_queue_size"), default=0),
            "events_processed": _as_int(snapshot.metrics.get("events_processed"), default=0),
            "event_type_counts": event_type_counts,
            "tool_audit_counts": {
                "allowed": _as_int(tool_audit_counts.get("allowed"), default=0),
                "denied": _as_int(tool_audit_counts.get("denied"), default=0),
            },
            "workers": workers,
            "current_event": current_event,
            "derived": derived,
        }
    )


def _derive_run_id(snapshot: Mapping[str, Any]) -> str:
    seed = {
        "timestamp": str(snapshot.get("timestamp", "")),
        "last_seen_event_id": _as_int(snapshot.get("last_seen_event_id"), default=0),
        "last_seen_tool_audit_id": _as_int(snapshot.get("last_seen_tool_audit_id"), default=0),
        "events_processed": _as_int(snapshot.get("events_processed"), default=0),
    }
    return f"phase4_{canonical_hash(seed)[:16]}"


def _adapt_agents(snapshot: Mapping[str, Any]) -> list[Dict[str, Any]]:
    workers = snapshot.get("workers")
    if not isinstance(workers, Mapping):
        return []

    agents: list[Dict[str, Any]] = []
    for agent_id_raw, worker_state_raw in sorted(workers.items(), key=lambda row: str(row[0]).lower()):
        if not isinstance(worker_state_raw, Mapping):
            continue
        agent_id = str(agent_id_raw).strip().lower()
        if not agent_id:
            continue
        agents.append(
            {
                "agent_id": agent_id,
                "present": bool(worker_state_raw.get("present", False)),
                "state": str(worker_state_raw.get("state", "IDLE")).upper(),
                "last_event_type": str(worker_state_raw.get("last_event_type", "")).upper(),
                "last_event_at": str(worker_state_raw.get("last_event_at", "")),
                "restart_count": _as_int(worker_state_raw.get("restart_count"), default=0),
                "missed_heartbeat_count": _as_int(worker_state_raw.get("missed_heartbeat_count"), default=0),
                "last_seen_event_id": _as_int(worker_state_raw.get("last_seen_event_id"), default=0),
            }
        )
    return agents


def _adapt_events(snapshot: Mapping[str, Any]) -> list[Dict[str, Any]]:
    timestamp = str(snapshot.get("timestamp", ""))
    events: list[Dict[str, Any]] = []

    current_event = snapshot.get("current_event")
    if isinstance(current_event, Mapping) and str(current_event.get("type", "")).strip():
        payload_raw = current_event.get("payload")
        payload = dict(payload_raw) if isinstance(payload_raw, Mapping) else {}
        events.append(
            {
                "event_id": _as_int(snapshot.get("last_seen_event_id"), default=0),
                "type": str(current_event.get("type", "")).upper(),
                "timestamp": str(current_event.get("timestamp", "")) or timestamp,
                "origin_id": str(current_event.get("origin_id", "")),
                "payload": payload,
            }
        )

    event_type_counts = snapshot.get("event_type_counts")
    if isinstance(event_type_counts, Mapping):
        for event_type_raw, count_raw in sorted(event_type_counts.items(), key=lambda row: str(row[0]).upper()):
            event_type = str(event_type_raw).strip().upper()
            if not event_type:
                continue
            events.append(
                {
                    "event_id": 0,
                    "type": event_type,
                    "timestamp": timestamp,
                    "origin_id": "projection_aggregate",
                    "payload": {
                        "count": _as_int(count_raw, default=0),
                        "kind": "event_type_count",
                    },
                }
            )

    return events


def _adapt_metrics(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    tool_audit_counts_raw = snapshot.get("tool_audit_counts")
    tool_audit_counts = (
        dict(tool_audit_counts_raw)
        if isinstance(tool_audit_counts_raw, Mapping)
        else {"allowed": 0, "denied": 0}
    )
    event_type_counts_raw = snapshot.get("event_type_counts")
    event_type_counts = dict(event_type_counts_raw) if isinstance(event_type_counts_raw, Mapping) else {}
    derived_raw = snapshot.get("derived")
    derived = dict(derived_raw) if isinstance(derived_raw, Mapping) else {}

    return {
        "running": bool(snapshot.get("running", False)),
        "event_queue_size": _as_int(snapshot.get("event_queue_size"), default=0),
        "events_processed": _as_int(snapshot.get("events_processed"), default=0),
        "last_seen_event_id": _as_int(snapshot.get("last_seen_event_id"), default=0),
        "last_seen_tool_audit_id": _as_int(snapshot.get("last_seen_tool_audit_id"), default=0),
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


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default
