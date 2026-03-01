from __future__ import annotations

from datetime import timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .utils import canonical_hash, parse_iso, to_int

_AREA_IDS = [
    "boardroom",
    "water_cooler",
    "supervisor_control_desk",
    "command_desk",
    "recon_desk",
    "forge_desk",
]

_AREA_EVENT_HINTS = {
    "boardroom": {"ARBITRATION_OUTCOME", "PROPOSAL_INVALID", "PROPOSAL_VOTE_MODIFIED"},
    "water_cooler": {"WATER_COOLER_LESSON"},
    "supervisor_control_desk": {"SUPERVISOR_START", "SUPERVISOR_STOP"},
    "command_desk": {"INTENT_DISPATCH"},
    "recon_desk": {"WORKER_STARTED", "WORKER_RESTARTED"},
    "forge_desk": {"WORKER_HEARTBEAT_MISSED", "WORKER_RESTART_SCHEDULED"},
}


def build_inspection_index(
    *,
    projection_snapshot: Mapping[str, Any],
    governance_entries: Iterable[Mapping[str, Any]],
    integrity_report: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    snapshot = projection_snapshot if isinstance(projection_snapshot, Mapping) else {}
    entries = [dict(entry) for entry in governance_entries if isinstance(entry, Mapping)]
    entries.sort(key=lambda row: to_int(row.get("seq"), default=0))
    report = integrity_report if isinstance(integrity_report, Mapping) else {}

    generated_at = str(snapshot.get("timestamp", "")) or str(report.get("generated_at", ""))
    entity_ids = _collect_entity_ids(snapshot, entries)
    registry = _latest_registry(entries)

    entity_summaries: Dict[str, Dict[str, Any]] = {}
    for entity_id in sorted(entity_ids):
        entity_summaries[entity_id] = _build_entity_summary(
            entity_id=entity_id,
            snapshot=snapshot,
            entries=entries,
            registry=registry,
        )

    for area_id in _AREA_IDS:
        entity_summaries[area_id] = _build_area_summary(area_id=area_id, snapshot=snapshot, entries=entries)

    office_timeline = _build_office_timeline(snapshot=snapshot, entries=entries)

    index = {
        "generated_at": generated_at,
        "entities": entity_summaries,
        "entity_ids": sorted(entity_summaries.keys()),
        "office_timeline": office_timeline,
        "integrity_summary": {
            "report_hash": report.get("report_hash"),
            "trust_trend": report.get("trust", {}).get("trend", {}),
            "propagation": report.get("propagation", {}),
            "arbitration_efficiency": report.get("arbitration", {}),
        },
        "cursor_state": {
            "entity_timeline_default_limit": 25,
            "office_timeline_default_limit": 50,
        },
    }
    index["index_hash"] = canonical_hash(index)
    return index


def paginate_timeline(
    timeline: List[Mapping[str, Any]],
    *,
    limit: int,
    cursor: str | None,
) -> Dict[str, Any]:
    page_limit = max(1, min(500, int(limit)))
    start = 0
    if isinstance(cursor, str) and cursor.strip():
        try:
            start = max(0, int(cursor))
        except Exception:
            start = 0
    items = timeline[start : start + page_limit]
    next_cursor = None
    if start + page_limit < len(timeline):
        next_cursor = str(start + page_limit)
    return {
        "items": items,
        "cursor": str(start),
        "next_cursor": next_cursor,
        "total": len(timeline),
    }


def _collect_entity_ids(snapshot: Mapping[str, Any], entries: List[Mapping[str, Any]]) -> set[str]:
    result: set[str] = set()
    workers = snapshot.get("workers")
    if isinstance(workers, Mapping):
        for worker_id in workers.keys():
            if isinstance(worker_id, str) and worker_id.strip():
                result.add(worker_id.strip().lower())

    for entry in entries:
        payload = entry.get("payload")
        if not isinstance(payload, Mapping):
            continue
        for key in ("subject_id", "target_agent", "agent_id"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                result.add(value.strip().lower())
        if isinstance(payload.get("votes"), list):
            for vote in payload["votes"]:
                if isinstance(vote, Mapping):
                    agent_id = vote.get("agent_id")
                    if isinstance(agent_id, str) and agent_id.strip():
                        result.add(agent_id.strip().lower())
    return result


def _latest_registry(entries: List[Mapping[str, Any]]) -> Mapping[str, Any]:
    for entry in reversed(entries):
        if str(entry.get("entry_type", "")).strip().upper() != "REGISTRY_UPDATE":
            continue
        payload = entry.get("payload")
        if not isinstance(payload, Mapping):
            continue
        registry = payload.get("registry")
        if isinstance(registry, Mapping):
            return registry
    return {}


def _build_entity_summary(
    *,
    entity_id: str,
    snapshot: Mapping[str, Any],
    entries: List[Mapping[str, Any]],
    registry: Mapping[str, Any],
) -> Dict[str, Any]:
    workers = snapshot.get("workers", {})
    worker_state = workers.get(entity_id, {}) if isinstance(workers, Mapping) else {}
    if not isinstance(worker_state, Mapping):
        worker_state = {}

    agents_map = registry.get("agents", {}) if isinstance(registry, Mapping) else {}
    agent_state = agents_map.get(entity_id, {}) if isinstance(agents_map, Mapping) else {}
    if not isinstance(agent_state, Mapping):
        agent_state = {}

    last_event_at = worker_state.get("last_event_at")
    snapshot_ts = snapshot.get("timestamp")
    age_seconds = _age_seconds(last_event_at=last_event_at, snapshot_timestamp=snapshot_ts)

    entity_timeline = _build_entity_timeline(entity_id=entity_id, snapshot=snapshot, entries=entries)
    recent_arbitration = [
        row for row in entity_timeline if str(row.get("entry_type", "")).upper() == "ARBITRATION_OUTCOME"
    ][:5]
    recent_trust = [row for row in entity_timeline if str(row.get("entry_type", "")).upper() == "TRUST_CHANGE"][:5]

    return {
        "id": entity_id,
        "entity_type": "agent",
        "role": agent_state.get("role", "worker"),
        "present": bool(worker_state.get("present", False)),
        "state": str(worker_state.get("state", "IDLE")),
        "age_seconds": age_seconds,
        "last_event_type": worker_state.get("last_event_type"),
        "last_event_at": worker_state.get("last_event_at"),
        "busy_with": _busy_with(entity_id=entity_id, snapshot=snapshot),
        "restart_count": to_int(worker_state.get("restart_count"), default=0),
        "missed_heartbeat_count": to_int(worker_state.get("missed_heartbeat_count"), default=0),
        "trust_snapshot": {
            "reputation_score": agent_state.get("reputation_score"),
            "trust_weights": agent_state.get("trust_weights", {}),
        },
        "recent_trust_changes": recent_trust,
        "recent_arbitration_outcomes": recent_arbitration,
        "timeline_total": len(entity_timeline),
    }


def _build_area_summary(
    *,
    area_id: str,
    snapshot: Mapping[str, Any],
    entries: List[Mapping[str, Any]],
) -> Dict[str, Any]:
    area_timeline = _build_area_timeline(area_id=area_id, snapshot=snapshot, entries=entries)
    occupants = _area_occupants(area_id=area_id, snapshot=snapshot)
    transitions = [row for row in area_timeline if row.get("source") == "governance_ledger"][:10]
    return {
        "id": area_id,
        "entity_type": "area",
        "occupants": occupants,
        "recent_occupancy_transitions": transitions,
        "timeline_total": len(area_timeline),
    }


def _build_office_timeline(*, snapshot: Mapping[str, Any], entries: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    timeline: List[Dict[str, Any]] = []
    timeline.extend(_events_from_snapshot(snapshot=snapshot))
    for entry in entries:
        timeline.extend(_events_from_ledger_entry(entry))
    timeline.sort(key=_timeline_sort_key)
    return timeline


def _build_entity_timeline(
    *,
    entity_id: str,
    snapshot: Mapping[str, Any],
    entries: List[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    office = _build_office_timeline(snapshot=snapshot, entries=entries)
    filtered = [item for item in office if entity_id in item.get("entity_ids", [])]
    return filtered


def _build_area_timeline(
    *,
    area_id: str,
    snapshot: Mapping[str, Any],
    entries: List[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    office = _build_office_timeline(snapshot=snapshot, entries=entries)
    filtered = [item for item in office if item.get("area_id") == area_id]
    return filtered


def _events_from_snapshot(*, snapshot: Mapping[str, Any]) -> List[Dict[str, Any]]:
    current_event = snapshot.get("current_event")
    if not isinstance(current_event, Mapping):
        return []
    event_type = str(current_event.get("type", "")).strip().upper()
    if not event_type:
        return []
    entity_ids = _event_entity_ids(current_event)
    event_id = to_int(snapshot.get("last_seen_event_id"), default=0)
    timestamp = current_event.get("timestamp") if isinstance(current_event.get("timestamp"), str) else snapshot.get("timestamp")
    area_id = _area_for_event(event_type)
    return [
        {
            "source": "projection_snapshot",
            "entry_type": event_type,
            "timestamp": timestamp,
            "event_id": event_id,
            "entity_ids": entity_ids,
            "area_id": area_id,
            "payload": dict(current_event),
        }
    ]


def _events_from_ledger_entry(entry: Mapping[str, Any]) -> List[Dict[str, Any]]:
    entry_type = str(entry.get("entry_type", "")).strip().upper()
    payload = entry.get("payload")
    if not isinstance(payload, Mapping):
        payload = {}
    event_id = to_int(payload.get("source_event_id"), default=to_int(entry.get("seq"), default=0))
    entity_ids = _payload_entity_ids(payload)
    area_id = _area_for_event(entry_type)
    return [
        {
            "source": "governance_ledger",
            "entry_type": entry_type,
            "timestamp": entry.get("timestamp"),
            "event_id": event_id,
            "entity_ids": entity_ids,
            "area_id": area_id,
            "payload": dict(payload),
            "seq": to_int(entry.get("seq"), default=0),
        }
    ]


def _event_entity_ids(event: Mapping[str, Any]) -> List[str]:
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        payload = {}
    ids = set()
    for key in ("target_agent", "agent_id", "worker"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            ids.add(value.strip().lower())
    origin = event.get("origin_id")
    if isinstance(origin, str) and origin.strip():
        ids.add(origin.strip().lower())
    return sorted(ids)


def _payload_entity_ids(payload: Mapping[str, Any]) -> List[str]:
    ids = set()
    for key in ("subject_id", "target_agent", "agent_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            ids.add(value.strip().lower())
    votes = payload.get("votes")
    if isinstance(votes, list):
        for vote in votes:
            if isinstance(vote, Mapping):
                voter = vote.get("agent_id")
                if isinstance(voter, str) and voter.strip():
                    ids.add(voter.strip().lower())
    lesson = payload.get("lesson")
    if isinstance(lesson, Mapping):
        recipients = lesson.get("recipients")
        if isinstance(recipients, list):
            for recipient in recipients:
                if isinstance(recipient, str) and recipient.strip():
                    ids.add(recipient.strip().lower())
        source_agent = lesson.get("source_agent")
        if isinstance(source_agent, str) and source_agent.strip():
            ids.add(source_agent.strip().lower())
    return sorted(ids)


def _timeline_sort_key(item: Mapping[str, Any]) -> Tuple[int, int, str, str]:
    event_id = item.get("event_id")
    if isinstance(event_id, int) and event_id > 0:
        return (0, event_id, "", "")
    timestamp = item.get("timestamp")
    timestamp_key = timestamp if isinstance(timestamp, str) else ""
    payload = item.get("payload")
    payload_hash = canonical_hash(payload if isinstance(payload, Mapping) else {})
    return (1, 0, timestamp_key, payload_hash)


def _busy_with(*, entity_id: str, snapshot: Mapping[str, Any]) -> str:
    workers = snapshot.get("workers")
    worker_state = workers.get(entity_id, {}) if isinstance(workers, Mapping) else {}
    if not isinstance(worker_state, Mapping):
        worker_state = {}

    current_event = snapshot.get("current_event")
    if isinstance(current_event, Mapping):
        entity_ids = _event_entity_ids(current_event)
        event_type = str(current_event.get("type", "")).strip().upper()
        if entity_id in entity_ids and event_type:
            return f"{event_type.lower()}"

    state = str(worker_state.get("state", "IDLE")).strip().upper()
    if state == "ACTIVE":
        return "active_processing"
    if state == "RESTARTING":
        return "restarting"
    if state == "OFFLINE":
        return "offline"
    return "idle"


def _age_seconds(*, last_event_at: Any, snapshot_timestamp: Any) -> int | None:
    start = parse_iso(last_event_at)
    end = parse_iso(snapshot_timestamp)
    if start is None or end is None:
        return None
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    if end < start:
        return 0
    return int((end - start).total_seconds())


def _area_for_event(event_type: str) -> str:
    normalized = str(event_type).strip().upper()
    for area_id, event_types in _AREA_EVENT_HINTS.items():
        if normalized in event_types:
            return area_id
    return "boardroom"


def _area_occupants(*, area_id: str, snapshot: Mapping[str, Any]) -> List[str]:
    workers = snapshot.get("workers", {})
    if not isinstance(workers, Mapping):
        return []
    occupants: List[str] = []
    for worker_id, state in workers.items():
        if not isinstance(worker_id, str) or not isinstance(state, Mapping):
            continue
        present = bool(state.get("present", False))
        worker_state = str(state.get("state", "")).strip().upper()
        if not (present or worker_state in {"ACTIVE", "RESTARTING"}):
            continue
        if area_id.endswith("_desk"):
            desk_prefix = area_id.replace("_desk", "")
            if worker_id.strip().lower().startswith(desk_prefix):
                occupants.append(worker_id.strip().lower())
        elif area_id == "boardroom":
            occupants.append(worker_id.strip().lower())
        elif area_id == "water_cooler" and worker_state == "IDLE":
            occupants.append(worker_id.strip().lower())
        elif area_id == "supervisor_control_desk" and worker_id.strip().lower() == "supervisor":
            occupants.append(worker_id.strip().lower())
    occupants.sort()
    return occupants
