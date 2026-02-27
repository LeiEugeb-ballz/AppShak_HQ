from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

from appshak_substrate.types import SubstrateEvent

from .schemas import normalize_projection_view, utc_now_iso
from .view_store import ProjectionViewStore


class ProjectionProjector:
    """Read-only projector: durable events/tool audits -> materialized view."""

    def __init__(
        self,
        *,
        mail_store: Any,
        view_store: ProjectionViewStore,
        audit_fetch_limit: int = 100_000,
    ) -> None:
        self._mail_store = mail_store
        self._view_store = view_store
        self._audit_fetch_limit = max(1, int(audit_fetch_limit))

    def project_once(self) -> Dict[str, Any]:
        view = normalize_projection_view(self._view_store.load())

        events = self._safe_list_events()
        pending_count = sum(1 for event in events if _event_status(event) == "PENDING")
        max_event_id, latest_event = _max_event(events)

        cursor_event_id = int(view.get("last_seen_event_id", 0))
        new_events = [event for event in events if _event_id(event) > cursor_event_id]
        new_events.sort(key=_event_id)
        for event in new_events:
            self._apply_event(view, event)
            cursor_event_id = max(cursor_event_id, _event_id(event))

        cursor_audit_id = int(view.get("last_seen_tool_audit_id", 0))
        audits = self._safe_list_tool_audit(limit=self._audit_fetch_limit)
        new_audits = [row for row in audits if _audit_id(row) > cursor_audit_id]
        new_audits.sort(key=_audit_id)
        for row in new_audits:
            self._apply_tool_audit(view, row)
            cursor_audit_id = max(cursor_audit_id, _audit_id(row))

        timestamp = utc_now_iso()
        view["schema_version"] = int(view.get("schema_version", 1))
        view["timestamp"] = timestamp
        view["last_updated_at"] = timestamp
        view["last_seen_event_id"] = max(cursor_event_id, max_event_id)
        view["last_seen_tool_audit_id"] = cursor_audit_id
        view["event_queue_size"] = pending_count
        view["current_event"] = _event_snapshot(latest_event)

        return self._view_store.save(view)

    def _apply_event(self, view: Dict[str, Any], event: SubstrateEvent) -> None:
        event_type = str(getattr(event, "type", "")).strip().upper()
        if event_type:
            counts = view.setdefault("event_type_counts", {})
            counts[event_type] = int(counts.get(event_type, 0)) + 1

        view["events_processed"] = int(view.get("events_processed", 0)) + 1

        if event_type == "SUPERVISOR_START":
            view["running"] = True
        elif event_type == "SUPERVISOR_STOP":
            view["running"] = False

    def _apply_tool_audit(self, view: Dict[str, Any], row: Mapping[str, Any]) -> None:
        counts = view.setdefault("tool_audit_counts", {"allowed": 0, "denied": 0})
        if bool(row.get("allowed", False)):
            counts["allowed"] = int(counts.get("allowed", 0)) + 1
        else:
            counts["denied"] = int(counts.get("denied", 0)) + 1

    def _safe_list_events(self) -> list[SubstrateEvent]:
        list_events = getattr(self._mail_store, "list_events", None)
        if not callable(list_events):
            return []
        rows = list_events()
        events: list[SubstrateEvent] = []
        if not isinstance(rows, Iterable):
            return events
        for row in rows:
            try:
                events.append(SubstrateEvent.coerce(row))
            except Exception:
                continue
        return events

    def _safe_list_tool_audit(self, *, limit: int) -> list[Mapping[str, Any]]:
        list_tool_audit = getattr(self._mail_store, "list_tool_audit", None)
        if not callable(list_tool_audit):
            return []
        rows = list_tool_audit(limit=max(1, int(limit)))
        if not isinstance(rows, Iterable):
            return []
        out: list[Mapping[str, Any]] = []
        for row in rows:
            if isinstance(row, Mapping):
                out.append(row)
        return out


def _event_id(event: SubstrateEvent) -> int:
    raw_id = getattr(event, "event_id", None)
    return int(raw_id) if isinstance(raw_id, int) else 0


def _event_status(event: SubstrateEvent) -> str:
    raw_status = getattr(event, "status", "")
    return str(raw_status).strip().upper()


def _event_snapshot(event: Optional[SubstrateEvent]) -> Optional[Dict[str, Any]]:
    if event is None:
        return None
    event_payload = dict(getattr(event, "payload", {}) or {})
    return {
        "type": str(getattr(event, "type", "")),
        "timestamp": str(getattr(event, "timestamp", "")),
        "origin_id": str(getattr(event, "origin_id", "")),
        "payload": event_payload,
    }


def _max_event(events: Iterable[SubstrateEvent]) -> tuple[int, Optional[SubstrateEvent]]:
    max_id = 0
    latest: Optional[SubstrateEvent] = None
    for event in events:
        event_id = _event_id(event)
        if event_id >= max_id:
            max_id = event_id
            latest = event
    return max_id, latest


def _audit_id(row: Mapping[str, Any]) -> int:
    raw_id = row.get("id")
    try:
        return int(raw_id)
    except Exception:
        return 0
