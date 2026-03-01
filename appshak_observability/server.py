from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from appshak_projection.view_store import ProjectionViewStore

from .broadcaster import ObservabilityBroadcaster


class _ProjectionStateView:
    """Minimal state-view facade backed by the projection store."""

    def __init__(self, projection_store: ProjectionViewStore) -> None:
        self._projection_store = projection_store

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._projection_store.load())


def create_app(
    *,
    state_view: Any,
    projection_view_store: Optional[ProjectionViewStore] = None,
    event_bus: Optional[Any] = None,
    broadcaster: Optional[ObservabilityBroadcaster] = None,
    snapshot_poll_interval: float = 1.0,
    durable_poll_interval: float = 1.0,
) -> FastAPI:
    del event_bus  # Observability is projection-first; websocket emits projection updates only.
    resolved_projection_store = projection_view_store or ProjectionViewStore()
    stream_bridge = broadcaster or ObservabilityBroadcaster(
        state_view=state_view,
        event_bus=None,
        projection_view_store=resolved_projection_store,
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
        description="Read-only backend for projection snapshot and view update stream.",
        version="3.0.0",
        lifespan=_lifespan,
    )
    app.state.state_view = state_view
    app.state.projection_view_store = resolved_projection_store
    app.state.broadcaster = stream_bridge

    @app.get("/api/snapshot")
    async def snapshot() -> Dict[str, Any]:
        return dict(resolved_projection_store.load())

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
    projection_view_path: str | Path = "appshak_state/projection/view.json",
    snapshot_poll_interval: float = 1.0,
    durable_poll_interval: float = 1.0,
) -> FastAPI:
    del mailstore_db  # Retained CLI compatibility; projection path is the runtime source.
    projection_store = ProjectionViewStore(projection_view_path)
    state_view = _ProjectionStateView(projection_store)
    return create_app(
        state_view=state_view,
        projection_view_store=projection_store,
        event_bus=None,
        snapshot_poll_interval=snapshot_poll_interval,
        durable_poll_interval=durable_poll_interval,
    )


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
    parser.add_argument("--projection-view", type=str, default="appshak_state/projection/view.json")
    parser.add_argument("--snapshot-poll-interval", type=float, default=1.0)
    parser.add_argument("--durable-poll-interval", type=float, default=1.0)
    parser.add_argument("--log-level", type=str, default="info")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    app = build_standalone_app(
        mailstore_db=args.mailstore_db,
        projection_view_path=args.projection_view,
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
