from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

from appshak.event_bus import Event, EventType


class BaseAgent(ABC):
    """Critical abstraction for all AppShak agents."""

    agent_id: Optional[str] = None
    authority_level: Optional[int] = None

    def __init__(self, kernel: Any) -> None:
        self.kernel = kernel
        self.event_bus = kernel.event_bus
        self.global_memory = kernel.global_memory
        self.prime_directive = kernel.PRIME_DIRECTIVE

    @abstractmethod
    async def run(self) -> None:
        """Long-running agent loop."""

    async def publish(
        self,
        event: Union[Event, Dict[str, Any]],
    ) -> Event:
        """Exclusive bus communication path for agents."""
        published = await self.event_bus.publish(event)

        append_agent_event = getattr(self.global_memory, "append_agent_event", None)
        if callable(append_agent_event):
            agent_name = self.agent_id or "agent"
            result = append_agent_event(agent_name, published.to_dict())
            if inspect.isawaitable(result):
                await result

        return published

    def build_event(
        self,
        event_type: Union[EventType, str],
        payload: Optional[Dict[str, Any]] = None,
        *,
        justification: Optional[str] = None,
    ) -> Event:
        event_payload = dict(payload or {})
        event_payload["prime_directive_justification"] = self._resolve_justification(
            payload=event_payload,
            explicit_justification=justification,
        )

        normalized_type = event_type if isinstance(event_type, EventType) else EventType(str(event_type))
        return Event(
            type=normalized_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            origin_id=self.agent_id or "unknown_agent",
            payload=event_payload,
        )

    def justify_action(self, action: str, impact: str) -> str:
        """Generate a Prime Directive alignment sentence for publication."""
        return f"{action} advances the Prime Directive by {impact}"

    async def update_memory_and_metrics(self) -> None:
        """Optional per-cycle hook."""
        return None

    async def shutdown(self) -> None:
        """Optional shutdown hook."""
        return None

    def _resolve_justification(
        self,
        payload: Dict[str, Any],
        explicit_justification: Optional[str],
    ) -> str:
        candidate = (
            explicit_justification
            or payload.get("prime_directive_justification")
        )
        if isinstance(candidate, str) and candidate.strip():
            return candidate
        return self.justify_action("unknown_action", "maintaining operational continuity")