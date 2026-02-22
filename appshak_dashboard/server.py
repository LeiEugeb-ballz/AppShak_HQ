from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .data_adapter import DashboardDataAdapter


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_RESULTS_PATH = "appshak_state/phase2A_results.json"
RESULTS_PATH = os.getenv("APP_SHAK_RESULTS", DEFAULT_RESULTS_PATH)

adapter = DashboardDataAdapter(results_path=RESULTS_PATH)

app = FastAPI(
    title="AppShak Dashboard",
    description="Read-only instrumentation layer for baseline visualization.",
    version="1.0.0",
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    del request
    index_path = BASE_DIR / "templates" / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/api/baseline")
def baseline() -> dict:
    return adapter.load_baseline(rolling_window=10)
