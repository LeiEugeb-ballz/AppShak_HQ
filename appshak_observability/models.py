from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from pydantic import BaseModel, Field

CHANNEL_WORKER_STATUS_UPDATES = "worker_status_updates"
CHANNEL_RESTART_EVENTS = "restart_events"
CHANNEL_QUEUE_DEPTH = "queue_depth"
CHANNEL_VIEW_UPDATE = "view_update"
CHANNEL_PLUGIN_EVENTS = "plugin_events"
CHANNEL_INTENT_DISPATCH_EVENTS = "intent_dispatch_events"
CHANNEL_TOOL_EXECUTION_LOGS = "tool_execution_logs"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    if isinstance(value, Mapping):
        return {str(key): to_json_safe(raw) for key, raw in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [to_json_safe(item) for item in value]

    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return to_json_safe(value.to_dict())
        except Exception:
            return str(value)

    return str(value)


def coerce_event_dict(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}

    candidate = raw
    if hasattr(candidate, "to_dict") and callable(candidate.to_dict):
        try:
            candidate = candidate.to_dict()
        except Exception:
            candidate = {}

    if isinstance(candidate, Mapping):
        return {str(key): value for key, value in candidate.items()}

    return {"value": candidate}


class SnapshotEvent(BaseModel):
    type: Optional[str] = None
    timestamp: Optional[str] = None
    origin_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "ignore"

    @classmethod
    def from_raw(cls, raw: Any) -> "SnapshotEvent":
        data = coerce_event_dict(raw)
        payload = data.get("payload", {})
        return cls(
            type=str(data.get("type")) if data.get("type") is not None else None,
            timestamp=_coerce_timestamp(data.get("timestamp")),
            origin_id=str(data.get("origin_id")) if data.get("origin_id") is not None else None,
            payload=to_json_safe(payload) if isinstance(payload, Mapping) else {},
        )


class SnapshotResponse(BaseModel):
    running: bool = False
    event_queue_size: int = 0
    current_event: Optional[SnapshotEvent] = None
    timestamp: str = Field(default_factory=utc_now_iso)

    class Config:
        extra = "ignore"

    @classmethod
    def from_snapshot(cls, raw: Any) -> "SnapshotResponse":
        data = coerce_event_dict(raw)
        event_queue_size = _coerce_int(data.get("event_queue_size"), default=0)
        current_event_raw = data.get("current_event")
        return cls(
            running=bool(data.get("running", False)),
            event_queue_size=max(0, event_queue_size),
            current_event=SnapshotEvent.from_raw(current_event_raw) if current_event_raw is not None else None,
            timestamp=_coerce_timestamp(data.get("timestamp")),
        )


class StreamEnvelope(BaseModel):
    channel: str
    timestamp: str = Field(default_factory=utc_now_iso)
    source: str = "unknown"
    data: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "ignore"

    @classmethod
    def build(
        cls,
        *,
        channel: str,
        data: Any,
        source: str,
        timestamp: Optional[Any] = None,
    ) -> "StreamEnvelope":
        payload = data if isinstance(data, Mapping) else {"value": data}
        return cls(
            channel=str(channel),
            timestamp=_coerce_timestamp(timestamp),
            source=str(source),
            data=to_json_safe(payload),
        )


def _coerce_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _coerce_timestamp(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return utc_now_iso()
