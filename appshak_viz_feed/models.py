from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Mapping

SAFE_PAYLOAD_KEYS = {"phase", "room_hint", "severity", "status", "target_role", "outcome", "activity"}
JOB_ID_KEYS = ("job_id", "plan_id")
CORRELATION_ID_KEYS = ("correlation_id",)
SCHEMA_VERSION = "viz_event/1.0"
WORK_START_EVENT_TYPES = {"INTENT_DISPATCH", "PROPOSAL", "WORKER_STARTED"}
WORK_FINISH_EVENT_TYPES = {"EXTERNAL_ACTION_RESULT", "PROPOSAL_INVALID", "CONSTITUTION_VIOLATION", "WORKER_EXITED", "KERNEL_SHUTDOWN", "SUPERVISOR_STOP"}
RECOVERY_EVENT_TYPES = {"KERNEL_RECOVERY", "WORKER_RESTART_SCHEDULED", "WORKER_RESTARTED", "KERNEL_START"}

_ROLE_BY_ORIGIN = {
    "command": "chief",
    "forge": "builder",
    "kernel": "kernel",
    "operator": "operator",
    "recon": "scout",
    "supervisor": "supervisor",
}

_PHASE_BY_TYPE = {
    "AGENT_STATUS": "IDLE",
    "CONSTITUTION_VIOLATION": "BLOCKED",
    "EXTERNAL_ACTION_APPROVAL": "APPROVAL",
    "EXTERNAL_ACTION_REQUEST": "APPROVAL",
    "EXTERNAL_ACTION_RESULT": "APPROVAL",
    "INTENT_DISPATCH": "INTAKE",
    "KERNEL_ERROR": "ERROR",
    "KERNEL_RECOVERY": "RECOVERY",
    "KERNEL_SHUTDOWN": "IDLE",
    "KERNEL_START": "RECOVERY",
    "PROPOSAL": "REVIEW",
    "PROPOSAL_DECISION": "REVIEW",
    "PROPOSAL_INVALID": "BLOCKED",
    "PROPOSAL_VOTE_MODIFIED": "REVIEW",
    "SUPERVISOR_START": "INTAKE",
    "SUPERVISOR_STOP": "IDLE",
    "WORKER_EXITED": "ERROR",
    "WORKER_HEARTBEAT_MISSED": "ERROR",
    "WORKER_RESTARTED": "RECOVERY",
    "WORKER_RESTART_SCHEDULED": "RECOVERY",
    "WORKER_STARTED": "BUILD",
}

_SEVERITY_BY_PHASE = {
    "APPROVAL": "info",
    "BLOCKED": "high",
    "BUILD": "info",
    "ERROR": "high",
    "IDLE": "low",
    "INTAKE": "info",
    "RECOVERY": "medium",
    "REVIEW": "medium",
}


def load_viz_schema() -> Dict[str, Any]:
    return json.loads(schema_path().read_text(encoding="utf-8"))


def schema_path() -> Path:
    return Path(__file__).resolve().with_name("viz_event.schema.json")


def build_viz_event(*, event: Mapping[str, Any], run_id: str, seq: int) -> Dict[str, Any]:
    event_type = str(event.get("type", "")).strip().upper()
    origin_id = str(event.get("origin_id", "")).strip() or "unknown"
    payload = event.get("payload")
    payload_map = dict(payload) if isinstance(payload, Mapping) else {}
    phase = _derive_phase(event_type=event_type, payload=payload_map)
    status = _derive_status(event_type=event_type, payload=payload_map)
    outcome = _derive_outcome(event_type=event_type, payload=payload_map)
    activity = _derive_activity(event_type=event_type, payload=payload_map, outcome=outcome, status=status)
    target_role = _derive_target_role(payload_map)
    room_hint = _safe_text(payload_map.get("room_hint"))
    severity = _safe_text(payload_map.get("severity")) or _SEVERITY_BY_PHASE.get(phase or "", "low")

    safe_payload: Dict[str, Any] = {}
    for key, value in (
        ("phase", phase),
        ("room_hint", room_hint),
        ("severity", severity),
        ("status", status),
        ("target_role", target_role),
        ("outcome", outcome),
        ("activity", activity),
    ):
        if value is not None:
            safe_payload[key] = value

    event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"appshak-viz:{run_id}:{seq}"))
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id,
        "run_id": str(run_id),
        "seq": int(seq),
        "ts": str(event.get("timestamp", "")),
        "type": event_type,
        "origin_id": origin_id,
        "origin_role": _origin_role(origin_id),
        "job_id": _pick_safe_identifier(payload_map, JOB_ID_KEYS),
        "correlation_id": _pick_safe_identifier(payload_map, CORRELATION_ID_KEYS),
        "payload": safe_payload,
    }


def validate_viz_event(event: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    schema_version = event.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        errors.append(f"schema_version must equal {SCHEMA_VERSION}")

    required_str_fields = ("event_id", "run_id", "ts", "type", "origin_id", "origin_role")
    for field in required_str_fields:
        value = event.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field} must be a non-empty string")

    seq = event.get("seq")
    if not isinstance(seq, int) or seq <= 0:
        errors.append("seq must be a positive integer")

    for field in ("job_id", "correlation_id"):
        value = event.get(field)
        if value is not None and not isinstance(value, str):
            errors.append(f"{field} must be null or string")

    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        errors.append("payload must be an object")
    else:
        for key in payload.keys():
            if key not in SAFE_PAYLOAD_KEYS:
                errors.append(f"payload.{key} is not allowed")
        for key, value in payload.items():
            if value is not None and not isinstance(value, str):
                errors.append(f"payload.{key} must be a string when present")
    return errors


def _origin_role(origin_id: str) -> str:
    normalized = origin_id.strip().lower()
    if normalized in _ROLE_BY_ORIGIN:
        return _ROLE_BY_ORIGIN[normalized]
    if normalized.startswith("worker:"):
        return "worker"
    if normalized:
        return "plugin"
    return "unknown"


def _derive_phase(*, event_type: str, payload: Mapping[str, Any]) -> str | None:
    if event_type == "EXTERNAL_ACTION_RESULT":
        status = _safe_text(payload.get("status"))
        if status and ("blocked" in status or "denied" in status):
            return "BLOCKED"
        if status and "executed" in status:
            return "APPROVAL"
    return _safe_text(payload.get("phase")) or _PHASE_BY_TYPE.get(event_type)


def _derive_status(*, event_type: str, payload: Mapping[str, Any]) -> str | None:
    explicit = _safe_text(payload.get("status"))
    if explicit:
        return explicit
    if event_type == "EXTERNAL_ACTION_APPROVAL":
        approved = payload.get("approved")
        if approved is True:
            return "approved"
        if approved is False:
            return "denied"
    if event_type == "CONSTITUTION_VIOLATION":
        return "blocked"
    if event_type in {"KERNEL_ERROR", "WORKER_EXITED", "WORKER_HEARTBEAT_MISSED"}:
        return "error"
    if event_type in {"KERNEL_RECOVERY", "WORKER_RESTARTED", "WORKER_RESTART_SCHEDULED"}:
        return "recovery"
    return None


def _derive_outcome(*, event_type: str, payload: Mapping[str, Any]) -> str | None:
    if event_type == "EXTERNAL_ACTION_APPROVAL":
        approved = payload.get("approved")
        if approved is True:
            return "APPROVED"
        if approved is False:
            return "DENIED"

    if event_type == "EXTERNAL_ACTION_RESULT":
        status = _safe_text(payload.get("status")) or ""
        if "executed" in status:
            return "EXECUTED"
        if "denied" in status:
            return "DENIED"
        if "blocked" in status:
            return "BLOCKED"
        if "failed" in status or "execution_denied" in status:
            return "FAILED"

    if event_type in {"CONSTITUTION_VIOLATION", "PROPOSAL_INVALID"}:
        return "BLOCKED"
    if event_type in {"KERNEL_ERROR", "WORKER_EXITED", "WORKER_HEARTBEAT_MISSED"}:
        return "FAILED"
    return None


def _derive_activity(
    *,
    event_type: str,
    payload: Mapping[str, Any],
    outcome: str | None,
    status: str | None,
) -> str | None:
    if event_type in WORK_START_EVENT_TYPES:
        return "START"
    if event_type in RECOVERY_EVENT_TYPES:
        return "RECOVERY"
    if outcome in {"DENIED", "BLOCKED", "EXECUTED", "FAILED"}:
        return "FINISH"
    if event_type in WORK_FINISH_EVENT_TYPES:
        return "FINISH"
    normalized_status = (status or "").lower()
    if event_type == "AGENT_STATUS" and "idle" in normalized_status:
        return "IDLE"
    if normalized_status in {"queued", "running", "approved", "recovery"}:
        return "ACTIVE"
    return "ACTIVE" if event_type else None


def _derive_target_role(payload: Mapping[str, Any]) -> str | None:
    target_role = _safe_text(payload.get("target_role"))
    if target_role:
        return target_role
    for key in ("target_agent", "agent_id", "worker"):
        candidate = _safe_text(payload.get(key))
        if candidate:
            return _origin_role(candidate)
    return None


def _pick_safe_identifier(payload: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        candidate = _safe_text(payload.get(key))
        if candidate:
            return candidate
    return None


def _safe_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None
