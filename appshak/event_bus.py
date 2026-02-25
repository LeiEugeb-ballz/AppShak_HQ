from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from itertools import count
from typing import Any, Callable, Dict, List, Optional, Union


class EventType(str, Enum):
    PROPOSAL = "PROPOSAL"
    PROPOSAL_INVALID = "PROPOSAL_INVALID"
    PROPOSAL_DECISION = "PROPOSAL_DECISION"
    PROPOSAL_VOTE_MODIFIED = "PROPOSAL_VOTE_MODIFIED"
    EXTERNAL_ACTION_REQUEST = "EXTERNAL_ACTION_REQUEST"
    EXTERNAL_ACTION_RESULT = "EXTERNAL_ACTION_RESULT"
    CONSTITUTION_VIOLATION = "CONSTITUTION_VIOLATION"
    KERNEL_START = "KERNEL_START"
    KERNEL_SHUTDOWN = "KERNEL_SHUTDOWN"
    KERNEL_ERROR = "KERNEL_ERROR"
    KERNEL_RECOVERY = "KERNEL_RECOVERY"
    AGENT_STATUS = "AGENT_STATUS"
    INTENT_DISPATCH = "INTENT_DISPATCH"


@dataclass(slots=True)
class Event:
    """Event contract for inter-agent communication over the EventBus."""

    type: EventType
    timestamp: str
    origin_id: str
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def origin(self) -> str:
        return self.origin_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "timestamp": self.timestamp,
            "origin_id": self.origin_id,
            "payload": dict(self.payload),
        }


class EventBus:
    """Async FIFO event transport with deterministic ordering."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._publish_lock = asyncio.Lock()
        self._publish_hooks: List[Callable[[Event], Any]] = []
        self._counter = count(start=1)

    async def publish(self, event: Union[Event, Dict[str, Any]]) -> Event:
        """Publish an event to the queue."""
        async with self._publish_lock:
            normalized = self._normalize(event, queue_index=next(self._counter))
            await self._queue.put(normalized)

        for hook in list(self._publish_hooks):
            try:
                hook_result = hook(normalized)
                if inspect.isawaitable(hook_result):
                    await hook_result
            except Exception:
                continue
        return normalized

    async def get_next(self, timeout: Optional[float] = None) -> Optional[Event]:
        """Get the next event, or None when timeout is reached."""
        if timeout is None:
            return await self._queue.get()

        if timeout <= 0:
            try:
                return self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return None

        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def add_publish_hook(self, hook: Callable[[Event], Any]) -> None:
        self._publish_hooks.append(hook)

    def qsize(self) -> int:
        return self._queue.qsize()

    @staticmethod
    def _normalize(event: Union[Event, Dict[str, Any]], queue_index: int) -> Event:
        if isinstance(event, Event):
            payload = dict(event.payload)
            payload.setdefault("queue_index", queue_index)
            return Event(
                type=event.type,
                timestamp=event.timestamp or EventBus._iso_now(),
                origin_id=event.origin_id,
                payload=payload,
            )

        raw_type = event.get("type")
        if isinstance(raw_type, EventType):
            event_type = raw_type
        elif isinstance(raw_type, str) and raw_type.strip():
            event_type = EventType(raw_type.strip())
        else:
            raise ValueError("Event must include a valid 'type'.")

        timestamp = event.get("timestamp")
        if not isinstance(timestamp, str) or not timestamp.strip():
            timestamp = EventBus._iso_now()

        raw_payload = event.get("payload")
        payload: Dict[str, Any] = dict(raw_payload) if isinstance(raw_payload, dict) else {}
        payload.setdefault("queue_index", queue_index)

        origin_id = event.get("origin_id") or event.get("origin") or payload.get("origin_id")
        if not isinstance(origin_id, str) or not origin_id.strip():
            raise ValueError("Event must include a non-empty 'origin_id'.")

        return Event(
            type=event_type,
            timestamp=timestamp,
            origin_id=origin_id.strip(),
            payload=payload,
        )

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat()
