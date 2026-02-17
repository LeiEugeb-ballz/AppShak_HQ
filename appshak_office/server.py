"""FastAPI server — serves the Office dashboard and WebSocket event stream."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from appshak_office.kernel import OfficeKernel

app = FastAPI(title="AppShak Office", version="2.0.0")

KERNEL_CONFIG = {
    "heartbeat_interval": 10,
    "event_poll_timeout": 1.0,
    "storage_root": "appshak_office_state",
}

kernel: OfficeKernel | None = None


@app.on_event("startup")
async def startup() -> None:
    global kernel
    kernel = OfficeKernel(KERNEL_CONFIG)
    await kernel.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    global kernel
    if kernel:
        await kernel.shutdown()


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    html_path = Path(__file__).parent / "dashboard.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/api/metrics")
async def metrics() -> dict[str, Any]:
    if kernel:
        return kernel.get_metrics()
    return {"error": "Kernel not running"}


@app.get("/api/events")
async def events() -> list[dict[str, Any]]:
    if kernel:
        return kernel.event_bus.event_log[-100:]
    return []


@app.get("/api/memory")
async def memory() -> dict[str, Any]:
    if kernel:
        return {
            "metrics": kernel.org_memory.get_metrics_summary(),
            "projects": [
                {
                    "id": p.project_id,
                    "name": p.name,
                    "domain": p.domain,
                    "status": p.status,
                }
                for p in kernel.org_memory.projects.values()
            ],
            "known_domains": list(kernel.org_memory.known_domains.keys()),
        }
    return {}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    if not kernel:
        await ws.close()
        return
    
    kernel.event_bus.add_ws_client(ws)
    try:
        while True:
            data = await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        kernel.event_bus.remove_ws_client(ws)
