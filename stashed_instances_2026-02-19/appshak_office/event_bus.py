"""
Event Bus — Shared communication channel for all agents.
Direct agent-to-agent communication is prohibited; all interactions go through the bus.
"""
from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from itertools import count
from typing import Any, Callable, Dict, List, Optional, Set, Union

from fastapi import WebSocket


class EventType(str, Enum):
    # Core workflow events
    PROPOSAL = "PROPOSAL"
    PROPOSAL_DECISION = "PROPOSAL_DECISION"
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_COMPLETE = "TASK_COMPLETE"
    ESCALATE_DECISION = "ESCALATE_DECISION"
    
    # External action events
    EXTERNAL_ACTION_REQUEST = "EXTERNAL_ACTION_REQUEST"
    EXTERNAL_ACTION_RESULT = "EXTERNAL_ACTION_RESULT"
    
    # System events
    KERNEL_START = "KERNEL_START"
    KERNEL_SHUTDOWN = "KERNEL_SHUTDOWN"
    KERNEL_ERROR = "KERNEL_ERROR"
    KERNEL_RECOVERY = "KERNEL_RECOVERY"
    CONSTITUTION_VIOLATION = "CONSTITUTION_VIOLATION"
    
    # Agent events
    AGENT_STATUS = "AGENT_STATUS"
    PROBLEM_DISCOVERED = "PROBLEM_DISCOVERED"
    PLAN_CREATED = "PLAN_CREATED"
    
    # Office metaphor events
    WATER_COOLER_START = "WATER_COOLER_START"
    WATER_COOLER_EXCHANGE = "WATER_COOLER_EXCHANGE"
    WATER_COOLER_END = "WATER_COOLER_END"
    BOARDROOM_CONVENE = "BOARDROOM_CONVENE"
    BOARDROOM_DISCUSSION = "BOARDROOM_DISCUSSION"
    BOARDROOM_DECISION = "BOARDROOM_DECISION"
    BOARDROOM_ADJOURN = "BOARDROOM_ADJOURN"
    PROJECT_LAUNCH = "PROJECT_LAUNCH"
    UPSKILL_SESSION = "UPSKILL_SESSION"
    
    # Memory events
    MEMORY_UPDATE = "MEMORY_UPDATE"
    RELATIONSHIP_UPDATE = "RELATIONSHIP_UPDATE"


@dataclass(slots=True)
class Event:
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
    """Async FIFO event transport with WebSocket broadcast."""
    
    def __init__(self) -> None:
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._publish_lock = asyncio.Lock()
        self._publish_hooks: List[Callable[[Event], Any]] = []
        self._counter = count(start=1)
        self._ws_clients: Set[WebSocket] = set()
        self._event_log: List[Dict[str, Any]] = []
        self._subscribers: Dict[EventType, List[Callable[[Event], Any]]] = {}
    
    def add_ws_client(self, ws: WebSocket) -> None:
        self._ws_clients.add(ws)
    
    def remove_ws_client(self, ws: WebSocket) -> None:
        self._ws_clients.discard(ws)
    
    @property
    def event_log(self) -> List[Dict[str, Any]]:
        return list(self._event_log)
    
    def subscribe(self, event_type: EventType, handler: Callable[[Event], Any]) -> None:
        """Subscribe to specific event types."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
    
    async def publish(self, event: Union[Event, Dict[str, Any]]) -> Event:
        async with self._publish_lock:
            normalized = self._normalize(event, queue_index=next(self._counter))
            await self._queue.put(normalized)
        
        event_dict = normalized.to_dict()
        self._event_log.append(event_dict)
        if len(self._event_log) > 1000:
            self._event_log = self._event_log[-1000:]
        
        # Broadcast to WebSocket clients
        await self._broadcast_ws(event_dict)
        
        # Notify subscribers
        handlers = self._subscribers.get(normalized.type, [])
        for handler in handlers:
            try:
                result = handler(normalized)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                pass
        
        # Run publish hooks
        for hook in list(self._publish_hooks):
            try:
                result = hook(normalized)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                pass
        
        return normalized
    
    async def _broadcast_ws(self, event_dict: Dict[str, Any]) -> None:
        dead: List[WebSocket] = []
        msg = json.dumps({"type": "event", "data": event_dict})
        for ws in list(self._ws_clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws_clients.discard(ws)
    
    async def get_next(self, timeout: Optional[float] = None) -> Optional[Event]:
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
