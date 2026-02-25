from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from appshak.plugins.runtime import KernelStateView
from appshak_substrate.bus_adapter import DurableEventBus
from appshak_substrate.mailstore_sqlite import SQLiteMailStore

from .broadcaster import ObservabilityBroadcaster
from .models import SnapshotResponse


class _KernelProxy:
    """Minimal kernel-shaped adapter for standalone observability runtime."""

    def __init__(self, *, event_bus: Any, running: bool = False) -> None:
        self.event_bus = event_bus
        self.running = bool(running)


def create_app(
    *,
    state_view: Any,
    event_bus: Optional[Any] = None,
    broadcaster: Optional[ObservabilityBroadcaster] = None,
    snapshot_poll_interval: float = 1.0,
    durable_poll_interval: float = 1.0,
) -> FastAPI:
    resolved_event_bus = event_bus if event_bus is not None else _extract_event_bus(state_view)
    stream_bridge = broadcaster or ObservabilityBroadcaster(
        state_view=state_view,
        event_bus=resolved_event_bus,
        snapshot_poll_interval=snapshot_poll_interval,
        durable_poll_interval=durable_poll_interval,
    )

    @asynccontextmanager
    async def _lifespan(_: FastAPI):
        await stream_bridge.start()
        try:
            yield
        finally:
            await stream_bridge.stop()

    app = FastAPI(
        title="AppShak Observability Backend",
        description="Read-only backend for kernel snapshot and live event telemetry.",
        version="3.0.0",
        lifespan=_lifespan,
    )
    app.state.state_view = state_view
    app.state.broadcaster = stream_bridge

    @app.get("/api/snapshot", response_model=SnapshotResponse)
    async def snapshot() -> SnapshotResponse:
        return SnapshotResponse.from_snapshot(state_view.snapshot())

    @app.websocket("/ws/events")
    async def ws_events(websocket: WebSocket) -> None:
        await websocket.accept()
        queue = stream_bridge.subscribe()
        try:
            while True:
                envelope = await queue.get()
                await websocket.send_json(_model_to_dict(envelope))
        except WebSocketDisconnect:
            return
        finally:
            stream_bridge.unsubscribe(queue)

    return app


def build_standalone_app(
    *,
    mailstore_db: str | Path,
    snapshot_poll_interval: float = 1.0,
    durable_poll_interval: float = 1.0,
) -> FastAPI:
    mail_store = SQLiteMailStore(mailstore_db)
    event_bus = DurableEventBus(
        mail_store=mail_store,
        consumer_id="observability",
        include_unrouted=True,
    )
    kernel_proxy = _KernelProxy(event_bus=event_bus, running=False)
    state_view = KernelStateView(kernel_proxy)
    return create_app(
        state_view=state_view,
        event_bus=event_bus,
        snapshot_poll_interval=snapshot_poll_interval,
        durable_poll_interval=durable_poll_interval,
    )


def _extract_event_bus(state_view: Any) -> Optional[Any]:
    kernel = getattr(state_view, "_kernel", None)
    return getattr(kernel, "event_bus", None)


def _model_to_dict(model: object) -> dict:
    dump = getattr(model, "model_dump", None)
    if callable(dump):
        return dict(dump())
    as_dict = getattr(model, "dict", None)
    if callable(as_dict):
        return dict(as_dict())
    return dict(model)  # type: ignore[arg-type]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AppShak read-only observability backend.")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--mailstore-db", type=str, default="appshak_state/substrate/mailstore.db")
    parser.add_argument("--snapshot-poll-interval", type=float, default=1.0)
    parser.add_argument("--durable-poll-interval", type=float, default=1.0)
    parser.add_argument("--log-level", type=str, default="info")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    app = build_standalone_app(
        mailstore_db=args.mailstore_db,
        snapshot_poll_interval=args.snapshot_poll_interval,
        durable_poll_interval=args.durable_poll_interval,
    )
    import uvicorn

    uvicorn.run(
        app,
        host=args.host,
        port=max(1, int(args.port)),
        log_level=str(args.log_level),
    )


if __name__ == "__main__":
    main()
