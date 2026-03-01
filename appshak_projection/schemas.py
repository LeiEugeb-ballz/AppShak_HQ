from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

PROJECTION_SCHEMA_VERSION = 1
_WORKER_STATES = {"IDLE", "ACTIVE", "RESTARTING", "OFFLINE"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_projection_view() -> Dict[str, Any]:
    timestamp = utc_now_iso()
    return {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "timestamp": timestamp,
        "last_updated_at": timestamp,
        "last_seen_event_id": 0,
        "last_seen_tool_audit_id": 0,
        "running": False,
        "event_queue_size": 0,
        "current_event": None,
        "events_processed": 0,
        "event_type_counts": {},
        "tool_audit_counts": {"allowed": 0, "denied": 0},
        "workers": {},
        "derived": {"office_mode": "PAUSED", "stress_level": 0.0},
    }


def normalize_projection_view(raw: Any) -> Dict[str, Any]:
    base = default_projection_view()
    source = raw if isinstance(raw, Mapping) else {}

    schema_version = _as_int(source.get("schema_version"), default=PROJECTION_SCHEMA_VERSION)
    if schema_version <= 0:
        schema_version = PROJECTION_SCHEMA_VERSION

    base["schema_version"] = schema_version
    base["timestamp"] = _as_timestamp(source.get("timestamp"), fallback=base["timestamp"])
    base["last_updated_at"] = _as_timestamp(source.get("last_updated_at"), fallback=base["last_updated_at"])
    base["last_seen_event_id"] = max(0, _as_int(source.get("last_seen_event_id"), default=0))
    base["last_seen_tool_audit_id"] = max(0, _as_int(source.get("last_seen_tool_audit_id"), default=0))
    base["running"] = bool(source.get("running", False))
    base["event_queue_size"] = max(0, _as_int(source.get("event_queue_size"), default=0))
    base["events_processed"] = max(0, _as_int(source.get("events_processed"), default=0))

    raw_counts = source.get("event_type_counts")
    event_type_counts: Dict[str, int] = {}
    if isinstance(raw_counts, Mapping):
        for key, value in raw_counts.items():
            event_type = str(key).strip().upper()
            if not event_type:
                continue
            event_type_counts[event_type] = max(0, _as_int(value, default=0))
    base["event_type_counts"] = event_type_counts

    raw_tool_counts = source.get("tool_audit_counts")
    allowed = 0
    denied = 0
    if isinstance(raw_tool_counts, Mapping):
        allowed = max(0, _as_int(raw_tool_counts.get("allowed"), default=0))
        denied = max(0, _as_int(raw_tool_counts.get("denied"), default=0))
    base["tool_audit_counts"] = {"allowed": allowed, "denied": denied}

    current_event = source.get("current_event")
    base["current_event"] = _normalize_event(current_event)
    base["workers"] = _normalize_workers(source.get("workers"))
    base["derived"] = _derive_projection_fields(
        running=base["running"],
        event_queue_size=base["event_queue_size"],
    )

    return base


def _normalize_event(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, Mapping):
        return None

    payload_raw = raw.get("payload")
    payload = dict(payload_raw) if isinstance(payload_raw, Mapping) else {}
    event_type = raw.get("type")
    event_timestamp = raw.get("timestamp")
    origin_id = raw.get("origin_id")

    return {
        "type": str(event_type) if event_type is not None else None,
        "timestamp": str(event_timestamp) if event_timestamp is not None else None,
        "origin_id": str(origin_id) if origin_id is not None else None,
        "payload": payload,
    }


def _as_timestamp(value: Any, *, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return fallback


def _as_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _normalize_workers(raw: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(raw, Mapping):
        return {}

    workers: Dict[str, Dict[str, Any]] = {}
    for worker_id_raw, worker_state_raw in raw.items():
        worker_id = str(worker_id_raw).strip().lower()
        if not worker_id:
            continue
        workers[worker_id] = _normalize_worker_state(worker_state_raw)
    return workers


def _normalize_worker_state(raw: Any) -> Dict[str, Any]:
    source = raw if isinstance(raw, Mapping) else {}

    present = bool(source.get("present", False))
    state_raw = source.get("state")
    state = str(state_raw).strip().upper() if state_raw is not None else "IDLE"
    if state not in _WORKER_STATES:
        state = "IDLE"

    last_event_type_raw = source.get("last_event_type")
    last_event_type = (
        str(last_event_type_raw).strip().upper()
        if isinstance(last_event_type_raw, str) and last_event_type_raw.strip()
        else None
    )

    last_event_at_raw = source.get("last_event_at")
    last_event_at = str(last_event_at_raw) if isinstance(last_event_at_raw, str) and last_event_at_raw.strip() else None

    return {
        "present": present,
        "state": state,
        "last_event_type": last_event_type,
        "last_event_at": last_event_at,
        "restart_count": max(0, _as_int(source.get("restart_count"), default=0)),
        "missed_heartbeat_count": max(0, _as_int(source.get("missed_heartbeat_count"), default=0)),
        "last_seen_event_id": max(0, _as_int(source.get("last_seen_event_id"), default=0)),
    }


def _derive_projection_fields(
    *,
    running: bool,
    event_queue_size: int,
) -> Dict[str, Any]:
    office_mode = "RUNNING" if bool(running) else "PAUSED"
    stress_level = min(max(0.0, float(event_queue_size)) / 25.0, 1.0)

    return {
        "office_mode": office_mode,
        "stress_level": stress_level,
    }
