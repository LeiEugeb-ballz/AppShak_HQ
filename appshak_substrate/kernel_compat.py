from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from appshak import AppShakKernel
from appshak_substrate.bus_adapter import DurableEventBus
from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.policy import ToolPolicy
from appshak_substrate.tool_gateway import ToolGateway


@dataclass(slots=True)
class KernelCompatibilityBundle:
    kernel: AppShakKernel
    mail_store: SQLiteMailStore
    event_bus: DurableEventBus
    tool_gateway: Optional[ToolGateway]


def build_kernel_with_substrate(
    *,
    config: Dict[str, Any],
    db_path: str | Path,
    consumer_id: str = "kernel",
    workspace_roots: Optional[Mapping[str, str | Path]] = None,
) -> KernelCompatibilityBundle:
    """Compatibility wrapper that injects substrate dependencies into kernel."""

    lease_seconds = float(config.get("mailstore_lease_seconds", 15.0))
    mail_store = SQLiteMailStore(db_path, lease_seconds=lease_seconds)
    event_bus = DurableEventBus(
        mail_store=mail_store,
        consumer_id=consumer_id,
        lease_seconds=lease_seconds,
    )

    tool_gateway = None
    if workspace_roots:
        tool_gateway = ToolGateway(
            mail_store=mail_store,
            policy=ToolPolicy(chief_agent_id="command"),
            workspace_roots=workspace_roots,
        )

    kernel = AppShakKernel(config, event_bus=event_bus, tool_gateway=tool_gateway)
    return KernelCompatibilityBundle(
        kernel=kernel,
        mail_store=mail_store,
        event_bus=event_bus,
        tool_gateway=tool_gateway,
    )
