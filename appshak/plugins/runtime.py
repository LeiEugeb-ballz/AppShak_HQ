from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


class KernelStateView:
    """Kernel-bound StateView implementation used by plugins."""

    def __init__(self, kernel: Any) -> None:
        self._kernel = kernel
        self._current_event: Optional[Any] = None

    def set_current_event(self, event: Optional[Any]) -> None:
        self._current_event = event

    def snapshot(self) -> Dict[str, Any]:
        queue_size = 0
        qsize = getattr(self._kernel.event_bus, "qsize", None)
        if callable(qsize):
            try:
                queue_size = int(qsize())
            except Exception:
                queue_size = 0

        current_event = self._current_event
        event_dict = None
        if current_event is not None:
            event_dict = (
                current_event.to_dict()
                if hasattr(current_event, "to_dict")
                else dict(current_event)
            )

        return {
            "running": bool(self._kernel.running),
            "event_queue_size": queue_size,
            "current_event": event_dict,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def emit_event(self, event: Dict[str, Any]) -> Any:
        if not isinstance(event, dict):
            raise TypeError("StateView.emit_event requires a dict event payload.")
        payload = event.get("payload", {})
        normalized_payload = dict(payload) if isinstance(payload, dict) else {}
        normalized_payload.setdefault(
            "prime_directive_justification",
            "Plugin action supports deterministic governance and execution continuity.",
        )
        raw = {
            "type": event.get("type"),
            "origin_id": event.get("origin_id") or "plugin",
            "timestamp": event.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            "payload": normalized_payload,
        }
        return await self._kernel.event_bus.publish(raw)

