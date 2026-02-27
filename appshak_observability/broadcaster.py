from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Dict, Mapping, Optional, Set, Tuple

from .models import (
    CHANNEL_INTENT_DISPATCH_EVENTS,
    CHANNEL_PLUGIN_EVENTS,
    CHANNEL_QUEUE_DEPTH,
    CHANNEL_RESTART_EVENTS,
    CHANNEL_TOOL_EXECUTION_LOGS,
    CHANNEL_VIEW_UPDATE,
    CHANNEL_WORKER_STATUS_UPDATES,
    SnapshotResponse,
    StreamEnvelope,
    coerce_event_dict,
)

_WORKER_STATUS_EVENT_TYPES = {
    "AGENT_STATUS",
    "SUPERVISOR_START",
    "SUPERVISOR_STOP",
    "SUPERVISOR_HEARTBEAT",
    "WORKER_STARTED",
    "WORKER_EXITED",
    "WORKER_HEARTBEAT_MISSED",
    "WORKER_DISABLED",
}

_RESTART_EVENT_TYPES = {
    "KERNEL_RECOVERY",
    "WORKER_RESTART_SCHEDULED",
    "WORKER_RESTARTED",
}

_TOOL_EVENT_TYPES = {
    "TOOL_REQUEST",
    "TOOL_RESULT",
}

_PLUGIN_EVENT_TYPES = {
    "PROPOSAL_INVALID",
    "PROPOSAL_VOTE_MODIFIED",
}

_CORE_ORIGINS = {
    "command",
    "forge",
    "kernel",
    "operator",
    "recon",
    "supervisor",
}


class ObservabilityBroadcaster:
    """Async fanout bridge for kernel/state-view observability."""

    def __init__(
        self,
        *,
        state_view: Any,
        event_bus: Optional[Any] = None,
        projection_view_store: Optional[Any] = None,
        snapshot_poll_interval: float = 1.0,
        durable_poll_interval: float = 1.0,
        ingress_queue_size: int = 1024,
        subscriber_queue_size: int = 256,
    ) -> None:
        self._state_view = state_view
        self._projection_view_store = projection_view_store
        self._event_bus = event_bus if event_bus is not None else self._resolve_event_bus(state_view)
        self._mail_store = getattr(self._event_bus, "mail_store", None) if self._event_bus is not None else None
        self._snapshot_poll_interval = max(0.1, float(snapshot_poll_interval))
        self._durable_poll_interval = max(0.1, float(durable_poll_interval))
        self._subscriber_queue_size = max(8, int(subscriber_queue_size))
        self._ingress_queue: "asyncio.Queue[StreamEnvelope]" = asyncio.Queue(maxsize=max(16, int(ingress_queue_size)))
        self._subscribers: Set["asyncio.Queue[StreamEnvelope]"] = set()
        self._tasks: list[asyncio.Task[Any]] = []
        self._running = False
        self._hook_registered = False
        self._last_queue_depth: Optional[int] = None
        self._last_view_fingerprint: Optional[Tuple[int, int, str]] = None
        self._seen_order: deque[str] = deque(maxlen=5000)
        self._seen_lookup: Set[str] = set()

    async def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._tasks = [
            asyncio.create_task(self._fanout_loop(), name="observability-fanout"),
            asyncio.create_task(self._snapshot_poll_loop(), name="observability-snapshot-poll"),
        ]

        if self._mail_store is not None and self._mail_store_supports_polling():
            self._tasks.append(
                asyncio.create_task(self._durable_poll_loop(), name="observability-durable-poll")
            )

        add_publish_hook = getattr(self._event_bus, "add_publish_hook", None)
        if callable(add_publish_hook) and not self._hook_registered:
            add_publish_hook(self._on_bus_event_published)
            self._hook_registered = True

    async def stop(self) -> None:
        if not self._running:
            return

        self._running = False
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        self._subscribers.clear()

    def subscribe(self) -> "asyncio.Queue[StreamEnvelope]":
        queue: "asyncio.Queue[StreamEnvelope]" = asyncio.Queue(maxsize=self._subscriber_queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: "asyncio.Queue[StreamEnvelope]") -> None:
        self._subscribers.discard(queue)

    async def _fanout_loop(self) -> None:
        while self._running:
            envelope = await self._ingress_queue.get()
            for subscriber in list(self._subscribers):
                self._enqueue_subscriber(subscriber, envelope)

    async def _snapshot_poll_loop(self) -> None:
        while self._running:
            try:
                raw_snapshot = await self._load_snapshot()
                snapshot = SnapshotResponse.from_snapshot(raw_snapshot)
                queue_depth = int(snapshot.event_queue_size)
                if self._last_queue_depth != queue_depth:
                    self._last_queue_depth = queue_depth
                    self._enqueue_ingress(
                        StreamEnvelope.build(
                            channel=CHANNEL_QUEUE_DEPTH,
                            source="state_view",
                            timestamp=snapshot.timestamp,
                            data={
                                "event_queue_size": queue_depth,
                                "running": snapshot.running,
                            },
                        )
                    )
                if self._projection_view_store is not None:
                    view_payload = coerce_event_dict(raw_snapshot)
                    view_fingerprint = self._view_fingerprint(view_payload)
                    if self._last_view_fingerprint != view_fingerprint:
                        self._last_view_fingerprint = view_fingerprint
                        self._enqueue_ingress(
                            StreamEnvelope.build(
                                channel=CHANNEL_VIEW_UPDATE,
                                source="projection_view",
                                timestamp=view_payload.get("timestamp"),
                                data={"view": view_payload},
                            )
                        )
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(self._snapshot_poll_interval)

    async def _load_snapshot(self) -> Dict[str, Any]:
        if self._projection_view_store is not None:
            load = getattr(self._projection_view_store, "load", None)
            if callable(load):
                raw = await asyncio.to_thread(load)
                return coerce_event_dict(raw)
        if self._state_view is None:
            return {}
        snapshot = getattr(self._state_view, "snapshot", None)
        if callable(snapshot):
            return coerce_event_dict(snapshot())
        return {}

    async def _durable_poll_loop(self) -> None:
        if self._mail_store is None:
            return

        last_event_id, last_audit_id = await self._bootstrap_durable_watermarks()
        while self._running:
            try:
                events = await asyncio.to_thread(self._mail_store.list_events)
                new_events: list[Tuple[int, Any]] = []
                for event in events:
                    raw_id = getattr(event, "event_id", None)
                    if isinstance(raw_id, int) and raw_id > last_event_id:
                        new_events.append((raw_id, event))
                new_events.sort(key=lambda item: item[0])
                for event_id, event in new_events:
                    last_event_id = max(last_event_id, event_id)
                    self._emit_event(event, source="durable_bus")

                audits = await asyncio.to_thread(self._mail_store.list_tool_audit, limit=500)
                new_audits: list[Tuple[int, Mapping[str, Any]]] = []
                for row in audits:
                    if not isinstance(row, Mapping):
                        continue
                    raw_id = row.get("id")
                    try:
                        audit_id = int(raw_id)
                    except Exception:
                        continue
                    if audit_id > last_audit_id:
                        new_audits.append((audit_id, row))
                new_audits.sort(key=lambda item: item[0])
                for audit_id, row in new_audits:
                    last_audit_id = max(last_audit_id, audit_id)
                    self._emit_tool_audit(row, source="durable_bus")
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(self._durable_poll_interval)

    async def _bootstrap_durable_watermarks(self) -> Tuple[int, int]:
        last_event_id = 0
        last_audit_id = 0
        if self._mail_store is None:
            return (last_event_id, last_audit_id)

        try:
            events = await asyncio.to_thread(self._mail_store.list_events)
            for event in events:
                raw_id = getattr(event, "event_id", None)
                if isinstance(raw_id, int):
                    last_event_id = max(last_event_id, raw_id)
        except Exception:
            pass

        try:
            latest_audits = await asyncio.to_thread(self._mail_store.list_tool_audit, limit=1)
            if latest_audits and isinstance(latest_audits[0], Mapping):
                last_audit_id = int(latest_audits[0].get("id", 0))
        except Exception:
            pass

        return (last_event_id, last_audit_id)

    async def _on_bus_event_published(self, event: Any) -> None:
        self._emit_event(event, source="event_bus")

    def _emit_event(self, event: Any, *, source: str) -> None:
        event_dict = coerce_event_dict(event)
        channel = self._classify_event_channel(event_dict)
        if channel is None:
            return

        dedupe_key = self._event_dedupe_key(channel, event_dict)
        if not self._mark_seen(dedupe_key):
            return

        timestamp = event_dict.get("timestamp")
        self._enqueue_ingress(
            StreamEnvelope.build(
                channel=channel,
                source=source,
                timestamp=timestamp,
                data={"event": event_dict},
            )
        )

    def _emit_tool_audit(self, row: Mapping[str, Any], *, source: str) -> None:
        try:
            audit_id = int(row.get("id"))
        except Exception:
            return

        dedupe_key = f"{CHANNEL_TOOL_EXECUTION_LOGS}:audit:{audit_id}"
        if not self._mark_seen(dedupe_key):
            return

        self._enqueue_ingress(
            StreamEnvelope.build(
                channel=CHANNEL_TOOL_EXECUTION_LOGS,
                source=source,
                timestamp=row.get("ts"),
                data={"audit": dict(row)},
            )
        )

    def _classify_event_channel(self, event: Mapping[str, Any]) -> Optional[str]:
        event_type = str(event.get("type", "")).strip().upper()
        if not event_type:
            return None

        if event_type == "INTENT_DISPATCH":
            return CHANNEL_INTENT_DISPATCH_EVENTS
        if event_type in _TOOL_EVENT_TYPES:
            return CHANNEL_TOOL_EXECUTION_LOGS
        if event_type in _RESTART_EVENT_TYPES:
            return CHANNEL_RESTART_EVENTS
        if event_type in _WORKER_STATUS_EVENT_TYPES:
            return CHANNEL_WORKER_STATUS_UPDATES
        if event_type in _PLUGIN_EVENT_TYPES:
            return CHANNEL_PLUGIN_EVENTS

        origin_id = str(event.get("origin_id", "")).strip().lower()
        if origin_id and origin_id not in _CORE_ORIGINS and not origin_id.startswith("worker:"):
            return CHANNEL_PLUGIN_EVENTS
        return None

    def _event_dedupe_key(self, channel: str, event: Mapping[str, Any]) -> str:
        payload = event.get("payload")
        payload_map = payload if isinstance(payload, Mapping) else {}
        raw_event_id = event.get("id", payload_map.get("event_id"))
        if isinstance(raw_event_id, int):
            return f"{channel}:event_id:{raw_event_id}"

        raw_queue_index = payload_map.get("queue_index")
        if isinstance(raw_queue_index, int):
            event_type = str(event.get("type", "")).strip().upper()
            origin_id = str(event.get("origin_id", "")).strip().lower()
            return f"{channel}:queue_index:{event_type}:{origin_id}:{raw_queue_index}"

        event_type = str(event.get("type", "")).strip().upper()
        origin_id = str(event.get("origin_id", "")).strip().lower()
        timestamp = str(event.get("timestamp", "")).strip()
        return f"{channel}:fallback:{event_type}:{origin_id}:{timestamp}"

    def _mark_seen(self, key: str) -> bool:
        if key in self._seen_lookup:
            return False
        if len(self._seen_order) == self._seen_order.maxlen:
            evicted = self._seen_order.popleft()
            self._seen_lookup.discard(evicted)
        self._seen_order.append(key)
        self._seen_lookup.add(key)
        return True

    def _enqueue_ingress(self, envelope: StreamEnvelope) -> None:
        if self._ingress_queue.full():
            try:
                self._ingress_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            self._ingress_queue.put_nowait(envelope)
        except asyncio.QueueFull:
            pass

    @staticmethod
    def _enqueue_subscriber(queue: "asyncio.Queue[StreamEnvelope]", envelope: StreamEnvelope) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(envelope)
        except asyncio.QueueFull:
            pass

    @staticmethod
    def _resolve_event_bus(state_view: Any) -> Optional[Any]:
        kernel = getattr(state_view, "_kernel", None)
        return getattr(kernel, "event_bus", None)

    def _mail_store_supports_polling(self) -> bool:
        return all(
            callable(getattr(self._mail_store, attr, None))
            for attr in ("list_events", "list_tool_audit")
        )

    @staticmethod
    def _view_fingerprint(payload: Mapping[str, Any]) -> Tuple[int, int, str]:
        last_seen_event_id = payload.get("last_seen_event_id")
        last_seen_tool_audit_id = payload.get("last_seen_tool_audit_id")
        timestamp = payload.get("timestamp")
        try:
            event_id = int(last_seen_event_id)
        except Exception:
            event_id = 0
        try:
            audit_id = int(last_seen_tool_audit_id)
        except Exception:
            audit_id = 0
        return (
            event_id,
            audit_id,
            str(timestamp) if isinstance(timestamp, str) else "",
        )
