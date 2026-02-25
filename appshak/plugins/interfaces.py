from __future__ import annotations

from typing import Any, Dict, Protocol


class StateView(Protocol):
    """Restricted plugin-facing access to kernel state and event emission."""

    def snapshot(self) -> Dict[str, Any]:
        ...

    async def emit_event(self, event: Dict[str, Any]) -> Any:
        ...


class AppShakPlugin(Protocol):
    """Plugin contract executed by the kernel each heartbeat cycle."""

    name: str

    async def dispatch(self, state_view: StateView) -> None:
        ...

