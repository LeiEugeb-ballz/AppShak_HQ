"""FastAPI server — serves dashboard and WebSocket event stream."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse

from appshak_live.kernel import AppShakKernel

app = FastAPI(title="AppShak Live", version="1.0.0")

KERNEL_CONFIG = {
    "heartbeat_interval": 4,
    "event_poll_timeout": 1.0,
    "safeguard_retry_max": 3,
    "safeguard_cooldown_seconds": 30,
    "endpoint_whitelist": [
        "https://api.appshak.io/v1/deploy",
        "https://api.appshak.io/v1/analyze",
        "https://api.appshak.io/v1/monitor",
        "https://api.appshak.io/v1/predict",
    ],
}

kernel: AppShakKernel | None = None


@app.on_event("startup")
async def startup() -> None:
    global kernel
    kernel = AppShakKernel(KERNEL_CONFIG)
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


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    if not kernel:
        await ws.close()
        return

    kernel.event_bus.add_ws_client(ws)
    try:
        while True:
            # Keep connection alive; client can send pings
            data = await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        kernel.event_bus.remove_ws_client(ws)
