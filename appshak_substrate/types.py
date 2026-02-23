from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Mapping, Optional


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class SubstrateEvent:
    """Event record used by the durable substrate."""

    type: str
    origin_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=iso_now)
    event_id: Optional[int] = None
    justification: Optional[str] = None
    status: str = "PENDING"
    error: Optional[str] = None
    correlation_id: Optional[str] = None
    target_agent: Optional[str] = None

    @property
    def id(self) -> Optional[int]:
        return self.event_id

    @property
    def ts(self) -> str:
        return self.timestamp

    @property
    def origin(self) -> str:
        return self.origin_id

    def to_dict(self) -> Dict[str, Any]:
        payload = dict(self.payload)
        if self.event_id is not None:
            payload.setdefault("event_id", self.event_id)
        return {
            "id": self.event_id,
            "type": self.type,
            "timestamp": self.timestamp,
            "origin_id": self.origin_id,
            "payload": payload,
            "justification": self.justification,
            "status": self.status,
            "error": self.error,
            "correlation_id": self.correlation_id,
            "target_agent": self.target_agent,
        }

    def payload_json(self) -> str:
        return json.dumps(self.payload, ensure_ascii=True)

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "SubstrateEvent":
        payload_raw = _row_value(row, "payload_json", "{}")
        payload = json.loads(payload_raw) if isinstance(payload_raw, str) and payload_raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
        event_id = _row_value(row, "id")
        if isinstance(event_id, int):
            payload.setdefault("event_id", event_id)
        target_agent = _row_value(row, "target_agent")
        if target_agent is None:
            payload_target = payload.get("target_agent")
            target_agent = payload_target if isinstance(payload_target, str) and payload_target.strip() else None
        return cls(
            event_id=event_id if isinstance(event_id, int) else None,
            timestamp=str(_row_value(row, "ts") or iso_now()),
            type=str(_row_value(row, "type") or ""),
            origin_id=str(_row_value(row, "origin_id") or "unknown"),
            payload=payload,
            justification=_row_value(row, "justification"),
            status=str(_row_value(row, "status") or "PENDING"),
            error=_row_value(row, "error"),
            correlation_id=_row_value(row, "correlation_id"),
            target_agent=target_agent,
        )

    @classmethod
    def coerce(cls, raw_event: Any) -> "SubstrateEvent":
        if isinstance(raw_event, cls):
            payload = dict(raw_event.payload)
            return cls(
                event_id=raw_event.event_id,
                type=str(raw_event.type),
                origin_id=str(raw_event.origin_id),
                payload=payload,
                timestamp=str(raw_event.timestamp or iso_now()),
                justification=raw_event.justification,
                status=str(raw_event.status or "PENDING"),
                error=raw_event.error,
                correlation_id=raw_event.correlation_id,
                target_agent=raw_event.target_agent,
            )

        if hasattr(raw_event, "to_dict") and callable(raw_event.to_dict):
            return cls.coerce(raw_event.to_dict())

        if isinstance(raw_event, Mapping):
            payload_raw = raw_event.get("payload", {})
            payload = dict(payload_raw) if isinstance(payload_raw, Mapping) else {}
            event_type = raw_event.get("type")
            normalized_type = str(getattr(event_type, "value", event_type) or "")
            if not normalized_type:
                raise ValueError("Event must include a non-empty type.")
            origin_id = raw_event.get("origin_id") or raw_event.get("origin") or payload.get("origin_id")
            if not isinstance(origin_id, str) or not origin_id.strip():
                raise ValueError("Event must include a non-empty origin_id.")
            timestamp = raw_event.get("timestamp")
            if not isinstance(timestamp, str) or not timestamp.strip():
                timestamp = iso_now()
            justification = raw_event.get("justification")
            if not isinstance(justification, str) or not justification.strip():
                payload_justification = payload.get("prime_directive_justification")
                justification = payload_justification if isinstance(payload_justification, str) else None
            target_agent = raw_event.get("target_agent")
            if not isinstance(target_agent, str) or not target_agent.strip():
                payload_target = payload.get("target_agent")
                target_agent = payload_target if isinstance(payload_target, str) and payload_target.strip() else None
            correlation_id = raw_event.get("correlation_id")
            if not isinstance(correlation_id, str) or not correlation_id.strip():
                payload_corr = payload.get("correlation_id")
                correlation_id = payload_corr if isinstance(payload_corr, str) and payload_corr.strip() else None
            event_id = raw_event.get("event_id") or raw_event.get("id")
            if isinstance(event_id, int):
                payload.setdefault("event_id", event_id)
            return cls(
                event_id=event_id if isinstance(event_id, int) else None,
                type=normalized_type,
                origin_id=origin_id.strip(),
                payload=payload,
                timestamp=timestamp,
                justification=justification,
                status=str(raw_event.get("status") or "PENDING"),
                error=raw_event.get("error"),
                correlation_id=correlation_id,
                target_agent=target_agent,
            )

        raise TypeError(f"Unsupported event type for coercion: {type(raw_event)!r}")


class ToolActionType(str, Enum):
    RUN_CMD = "RUN_CMD"
    WRITE_FILE = "WRITE_FILE"
    READ_FILE = "READ_FILE"
    GIT_COMMIT = "GIT_COMMIT"
    GIT_DIFF = "GIT_DIFF"
    OPEN_PR = "OPEN_PR"


@dataclass(slots=True)
class ToolRequest:
    agent_id: str
    action_type: ToolActionType
    working_dir: str
    payload: Dict[str, Any] = field(default_factory=dict)
    authorized_by: Optional[str] = None
    correlation_id: Optional[str] = None


@dataclass(slots=True)
class ToolResult:
    allowed: bool
    action_type: ToolActionType
    agent_id: str
    working_dir: str
    stdout: str = ""
    stderr: str = ""
    return_code: Optional[int] = None
    error: Optional[str] = None
    reason: Optional[str] = None
    audit_event_id: Optional[int] = None
    correlation_id: Optional[str] = None


def _row_value(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(key, default)
    try:
        return row[key]  # type: ignore[index]
    except Exception:
        return default
