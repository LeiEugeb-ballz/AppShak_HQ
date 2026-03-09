from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .coords_hq_v1 import assign_room_anchors
from .mapping_table import derive_room, derive_state
from .normalize import norm_activity, norm_origin_role, norm_outcome, norm_severity, sort_warnings

REQUIRED_ENVELOPE_FIELDS = {
    "schema_version",
    "event_id",
    "run_id",
    "seq",
    "ts",
    "type",
    "origin_id",
    "origin_role",
    "job_id",
    "correlation_id",
    "payload",
}


@dataclass
class ProjectionState:
    schema_version: str = "projection_state/1.0"
    run_id: str = ""
    last_seq_processed: int = -1
    viewer: Dict[str, Any] = field(default_factory=lambda: {"mode": "REPLAY", "viewer_time_utc": None})
    agents: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    jobs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    blocked_events: List[Dict[str, Any]] = field(default_factory=list)
    alerts: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    room_occupancy: Dict[str, List[str]] = field(default_factory=dict)


def _warn(ts: str, code: str, message: str, event_id: Optional[str] = None) -> Dict[str, Any]:
    return {"ts": ts, "code": code, "message": message, "event_id": event_id}


def validate_event_envelope(evt: Dict[str, Any]) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    missing = [key for key in REQUIRED_ENVELOPE_FIELDS if key not in evt]
    if missing:
        warnings.append(_warn(evt.get("ts", ""), "MALFORMED_EVENT", f"Missing fields: {missing}", evt.get("event_id")))
    return warnings


def reduce_event(prev: ProjectionState, evt: Dict[str, Any]) -> ProjectionState:
    st = ProjectionState(**asdict(prev))

    ts = evt.get("ts") or ""
    event_id = evt.get("event_id")

    env_warnings = validate_event_envelope(evt)
    if env_warnings:
        st.warnings.extend(env_warnings)
        return st

    run_id = str(evt["run_id"])
    seq = int(evt["seq"])
    if st.run_id and run_id != st.run_id:
        st.warnings.append(_warn(ts, "RUN_ID_CHANGED", f"run_id changed {st.run_id} -> {run_id}", event_id))
        st.run_id = run_id
        st.last_seq_processed = -1
    elif not st.run_id:
        st.run_id = run_id

    if seq <= st.last_seq_processed:
        st.warnings.append(_warn(ts, "SEQ_OUT_OF_ORDER", f"seq {seq} after {st.last_seq_processed}", event_id))
    else:
        st.last_seq_processed = seq
        st.viewer["viewer_time_utc"] = ts

    local_warnings: List[Dict[str, Any]] = []

    nr = norm_origin_role(evt.get("origin_role"))
    origin_role = nr.value or "UNKNOWN"
    if nr.warning:
        local_warnings.append(_warn(ts, nr.warning, f"origin_role={nr.raw!r}", event_id))

    payload = evt.get("payload") or {}
    sev = norm_severity(payload.get("severity"))
    if sev.warning:
        local_warnings.append(_warn(ts, sev.warning, f"severity={sev.raw!r}", event_id))

    act = norm_activity(payload.get("activity"))
    if act.warning:
        local_warnings.append(_warn(ts, act.warning, f"activity={act.raw!r}", event_id))

    out = norm_outcome(payload.get("outcome"))
    if out.warning:
        local_warnings.append(_warn(ts, out.warning, f"outcome={out.raw!r}", event_id))

    st.warnings.extend(sort_warnings(local_warnings))

    phase = payload.get("phase")
    phase = phase.strip().upper() if isinstance(phase, str) and phase.strip() else None
    activity = act.value
    outcome = out.value
    room_hint = payload.get("room_hint")

    origin_id = str(evt["origin_id"])
    job_id = evt.get("job_id")
    job_id = str(job_id) if isinstance(job_id, str) and job_id.strip() else None
    correlation_id = evt.get("correlation_id")
    correlation_id = str(correlation_id) if isinstance(correlation_id, str) and correlation_id.strip() else None

    room_id = derive_room(
        phase=phase,
        outcome=outcome,
        activity=activity,
        origin_role=origin_role,
        room_hint=room_hint,
    )
    state = derive_state(phase=phase, outcome=outcome, activity=activity)

    agent = st.agents.get(
        origin_id,
        {
            "origin_role": origin_role,
            "state": "UNKNOWN",
            "room_id": "unknown_room",
            "job_id": None,
            "last_ts": None,
            "flags": [],
        },
    )
    agent["origin_role"] = origin_role
    agent["state"] = state
    agent["room_id"] = room_id
    agent["job_id"] = job_id
    agent["last_ts"] = ts
    st.agents[origin_id] = agent

    if job_id:
        job = st.jobs.get(
            job_id,
            {
                "correlation_id": correlation_id,
                "status": "UNKNOWN",
                "phase": None,
                "outcome": None,
                "last_ts": None,
            },
        )
        if correlation_id and not job.get("correlation_id"):
            job["correlation_id"] = correlation_id
        if phase:
            job["phase"] = phase
        if outcome:
            job["outcome"] = outcome

        if outcome in {"BLOCKED", "DENIED"}:
            job["status"] = "BLOCKED"
        elif outcome == "EXECUTED":
            job["status"] = "DONE"
        elif phase in {"INTAKE", "BUILD", "APPROVAL", "ERROR", "RECOVERY"}:
            job["status"] = "IN_PROGRESS"

        job["last_ts"] = ts
        st.jobs[job_id] = job

    if outcome in {"BLOCKED", "DENIED"}:
        st.blocked_events.append({"event_id": event_id, "job_id": job_id, "outcome": outcome})

    sev_value = sev.value or "UNKNOWN"
    evt_type = str(evt.get("type") or "")
    if sev_value in {"HIGH", "CRITICAL"} or outcome in {"FAILED", "BLOCKED", "DENIED"} or "VIOLATION" in evt_type:
        st.alerts.append(
            {
                "ts": ts,
                "severity": sev_value,
                "code": evt_type,
                "job_id": job_id,
                "event_id": event_id,
            }
        )

    occupancy: Dict[str, List[str]] = {}
    for oid, current_agent in st.agents.items():
        rid = current_agent.get("room_id") or "unknown_room"
        occupancy.setdefault(rid, []).append(oid)
    for rid in occupancy:
        occupancy[rid] = sorted(occupancy[rid])
    st.room_occupancy = dict(sorted(occupancy.items(), key=lambda item: item[0]))

    for rid, origin_ids in st.room_occupancy.items():
        positions = assign_room_anchors(rid, origin_ids)
        for oid in origin_ids:
            st.agents[oid]["pos"] = positions[oid]

    return st


def initial_state(mode: str = "REPLAY") -> ProjectionState:
    st = ProjectionState()
    st.viewer = {"mode": mode, "viewer_time_utc": None}
    return st
