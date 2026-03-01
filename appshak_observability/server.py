from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Mapping, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from appshak_inspection.indexer import paginate_timeline
from appshak_projection.view_store import ProjectionViewStore

from .broadcaster import ObservabilityBroadcaster
from .models import SnapshotResponse
from .stores import ObservabilityDataStore


class _ProjectionStateView:
    def __init__(self, projection_view_store: ProjectionViewStore) -> None:
        self._projection_view_store = projection_view_store
        self._kernel = None

    def snapshot(self) -> Mapping[str, Any]:
        return self._projection_view_store.load()


def create_app(
    *,
    state_view: Optional[Any] = None,
    projection_view_store: Optional[ProjectionViewStore] = None,
    event_bus: Optional[Any] = None,
    broadcaster: Optional[ObservabilityBroadcaster] = None,
    data_store: Optional[ObservabilityDataStore] = None,
    snapshot_poll_interval: float = 1.0,
    durable_poll_interval: float = 1.0,
) -> FastAPI:
    resolved_projection_store = projection_view_store or ProjectionViewStore()
    resolved_state_view = state_view or _ProjectionStateView(resolved_projection_store)
    resolved_event_bus = event_bus if event_bus is not None else _extract_event_bus(resolved_state_view)
    resolved_data_store = data_store or ObservabilityDataStore()
    stream_bridge = broadcaster or ObservabilityBroadcaster(
        state_view=resolved_state_view,
        event_bus=resolved_event_bus,
        projection_view_store=resolved_projection_store,
        inspection_loader=resolved_data_store.inspection_store,
        integrity_loader=resolved_data_store.integrity_store,
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
        description="Read-only backend for snapshot, inspection, integrity and stability telemetry.",
        version="4.0.0",
        lifespan=_lifespan,
    )
    app.state.state_view = resolved_state_view
    app.state.projection_view_store = resolved_projection_store
    app.state.broadcaster = stream_bridge
    app.state.data_store = resolved_data_store

    @app.get("/api/snapshot", response_model=SnapshotResponse)
    async def snapshot() -> SnapshotResponse:
        return SnapshotResponse.from_snapshot(resolved_projection_store.load())

    @app.get("/api/inspect/entities")
    async def inspect_entities() -> dict:
        entities = resolved_data_store.load_entities()
        return {
            "items": entities,
            "count": len(entities),
        }

    @app.get("/api/inspect/entity/{entity_id}")
    async def inspect_entity(entity_id: str) -> dict:
        return resolved_data_store.load_entity(entity_id)

    @app.get("/api/inspect/entity/{entity_id}/timeline")
    async def inspect_entity_timeline(entity_id: str, limit: int = 25, cursor: str | None = None) -> dict:
        timeline = resolved_data_store.load_entity_timeline(entity_id)
        return paginate_timeline(timeline, limit=limit, cursor=cursor)

    @app.get("/api/inspect/office/timeline")
    async def inspect_office_timeline(limit: int = 50, cursor: str | None = None) -> dict:
        timeline = resolved_data_store.load_office_timeline()
        return paginate_timeline(timeline, limit=limit, cursor=cursor)

    @app.get("/api/integrity/latest")
    async def integrity_latest() -> dict:
        return resolved_data_store.load_integrity_latest()

    @app.get("/api/integrity/history")
    async def integrity_history(limit: int = 20, cursor: str | None = None) -> dict:
        return resolved_data_store.load_integrity_history(limit=limit, cursor=cursor)

    @app.get("/api/stability/runs")
    async def stability_runs() -> dict:
        runs = resolved_data_store.load_stability_runs()
        return {"items": runs, "count": len(runs)}

    @app.get("/api/stability/run/{run_id}")
    async def stability_run(run_id: str) -> dict:
        return resolved_data_store.load_stability_run(run_id)

    @app.get("/api/health")
    async def health() -> dict:
        snapshot_payload = resolved_projection_store.load()
        inspection_payload = resolved_data_store.inspection_store.load_latest()
        integrity_payload = resolved_data_store.integrity_store.load_latest()
        return {
            "status": "ok",
            "last_snapshot_time": _optional_string(snapshot_payload.get("timestamp")),
            "last_inspection_index_time": _optional_string(inspection_payload.get("generated_at")),
            "last_integrity_report_time": _optional_string(integrity_payload.get("generated_at")),
        }

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
    inspection_root: str | Path = "appshak_state/inspection",
    integrity_root: str | Path = "appshak_state/integrity",
    stability_root: str | Path = "appshak_state/stability",
    snapshot_poll_interval: float = 1.0,
    durable_poll_interval: float = 1.0,
) -> FastAPI:
    del mailstore_db
    projection_store = ProjectionViewStore(projection_view_path)
    state_view = _ProjectionStateView(projection_store)
    data_store = ObservabilityDataStore(
        inspection_root=inspection_root,
        integrity_root=integrity_root,
        stability_root=stability_root,
    )
    return create_app(
        state_view=state_view,
        projection_view_store=projection_store,
        data_store=data_store,
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


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AppShak read-only observability backend.")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--mailstore-db", type=str, default="appshak_state/substrate/mailstore.db")
    parser.add_argument("--projection-view", type=str, default="appshak_state/projection/view.json")
    parser.add_argument("--inspection-root", type=str, default="appshak_state/inspection")
    parser.add_argument("--integrity-root", type=str, default="appshak_state/integrity")
    parser.add_argument("--stability-root", type=str, default="appshak_state/stability")
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
        inspection_root=args.inspection_root,
        integrity_root=args.integrity_root,
        stability_root=args.stability_root,
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
