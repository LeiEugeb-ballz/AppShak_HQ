from __future__ import annotations

import asyncio
from typing import Any, Mapping, Optional, Set, Tuple

from .models import CHANNEL_VIEW_UPDATE, StreamEnvelope, coerce_event_dict


class ObservabilityBroadcaster:
    """Async fanout bridge for projection view updates."""

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
        del event_bus
        del durable_poll_interval
        self._state_view = state_view
        self._projection_view_store = projection_view_store
        self._snapshot_poll_interval = max(0.1, float(snapshot_poll_interval))
        self._subscriber_queue_size = max(8, int(subscriber_queue_size))
        self._ingress_queue: "asyncio.Queue[StreamEnvelope]" = asyncio.Queue(maxsize=max(16, int(ingress_queue_size)))
        self._subscribers: Set["asyncio.Queue[StreamEnvelope]"] = set()
        self._tasks: list[asyncio.Task[Any]] = []
        self._running = False
        self._last_view_fingerprint: Optional[Tuple[int, int, str]] = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._tasks = [
            asyncio.create_task(self._fanout_loop(), name="observability-fanout"),
            asyncio.create_task(self._snapshot_poll_loop(), name="observability-snapshot-poll"),
        ]

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

    async def _load_snapshot(self) -> Mapping[str, Any]:
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
