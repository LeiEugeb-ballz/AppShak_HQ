from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, List, Optional

from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.types import SubstrateEvent


class DurableEventBus:
    """EventBus-compatible adapter backed by SQLiteMailStore."""

    def __init__(
        self,
        mail_store: SQLiteMailStore,
        *,
        consumer_id: str = "kernel",
        target_agent: Optional[str] = None,
        include_unrouted: bool = True,
        lease_seconds: float = 15.0,
    ) -> None:
        self.mail_store = mail_store
        self.consumer_id = consumer_id
        self.target_agent = target_agent
        self.include_unrouted = include_unrouted
        self.lease_seconds = lease_seconds
        self._publish_lock = asyncio.Lock()
        self._publish_hooks: List[Callable[[SubstrateEvent], Any]] = []

    async def publish(self, event: Any) -> SubstrateEvent:
        async with self._publish_lock:
            normalized = SubstrateEvent.coerce(event)
            event_id = await asyncio.to_thread(self.mail_store.append_event, normalized)
            normalized.event_id = event_id
            normalized.payload.setdefault("event_id", event_id)
            normalized.payload.setdefault("queue_index", event_id)

        for hook in list(self._publish_hooks):
            try:
                res = hook(normalized)
                if inspect.isawaitable(res):
                    await res
            except Exception:
                continue
        return normalized

    async def get_next(self, timeout: Optional[float] = None) -> Optional[SubstrateEvent]:
        event = await asyncio.to_thread(
            self.mail_store.claim_next_event,
            self.consumer_id,
            timeout,
            target_agent=self.target_agent,
            include_unrouted=self.include_unrouted,
            lease_seconds=self.lease_seconds,
        )
        if event is None:
            return None
        event.payload.setdefault("event_id", event.event_id)
        event.payload.setdefault("queue_index", event.event_id)
        return event

    async def ack_event(self, event_or_id: Any, status: str = "DONE") -> None:
        event_id = self._extract_event_id(event_or_id)
        if event_id is None:
            return
        await asyncio.to_thread(
            self.mail_store.ack_event,
            event_id,
            status,
            consumer_id=self.consumer_id,
        )

    async def fail_event(self, event_or_id: Any, error: str) -> None:
        event_id = self._extract_event_id(event_or_id)
        if event_id is None:
            return
        await asyncio.to_thread(
            self.mail_store.fail_event,
            event_id,
            str(error),
            consumer_id=self.consumer_id,
        )

    async def requeue_event(self, event_or_id: Any, error: Optional[str] = None) -> None:
        event_id = self._extract_event_id(event_or_id)
        if event_id is None:
            return
        await asyncio.to_thread(
            self.mail_store.requeue_event,
            event_id,
            consumer_id=self.consumer_id,
            error=error,
        )

    def add_publish_hook(self, hook: Callable[[SubstrateEvent], Any]) -> None:
        self._publish_hooks.append(hook)

    def qsize(self) -> int:
        counts = self.mail_store.status_counts()
        return int(counts.get("PENDING", 0))

    @staticmethod
    def _extract_event_id(event_or_id: Any) -> Optional[int]:
        if isinstance(event_or_id, int):
            return event_or_id
        if hasattr(event_or_id, "event_id"):
            event_id = getattr(event_or_id, "event_id", None)
            return event_id if isinstance(event_id, int) else None
        if isinstance(event_or_id, dict):
            for key in ("event_id", "id"):
                value = event_or_id.get(key)
                if isinstance(value, int):
                    return value
            payload = event_or_id.get("payload")
            if isinstance(payload, dict):
                payload_id = payload.get("event_id")
                if isinstance(payload_id, int):
                    return payload_id
        return None
