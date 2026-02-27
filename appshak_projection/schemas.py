from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

PROJECTION_SCHEMA_VERSION = 1


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
