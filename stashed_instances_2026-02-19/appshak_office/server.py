"""FastAPI server — serves the Office dashboard and WebSocket event stream."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

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
    html_path = Path(__file__).parent / "dashboard_security.html"
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


# ── User Interaction Endpoints ──

# Pending approvals queue
pending_approvals: list[dict[str, Any]] = []


@app.get("/api/approvals")
async def get_pending_approvals() -> list[dict[str, Any]]:
    """Get all pending approval requests."""
    return pending_approvals


@app.post("/api/approve/{proposal_id}")
async def approve_proposal(proposal_id: str) -> dict[str, Any]:
    """Approve a pending proposal."""
    global pending_approvals
    approval = None
    for p in pending_approvals:
        if p.get("proposal_id") == proposal_id:
            approval = p
            break
    
    if approval:
        pending_approvals = [p for p in pending_approvals if p.get("proposal_id") != proposal_id]
        # Notify kernel
        if kernel:
            await kernel.event_bus.publish({
                "type": "USER_APPROVAL",
                "proposal_id": proposal_id,
                "decision": "approved",
                "timestamp": asyncio.get_event_loop().time()
            })
        return {"status": "approved", "proposal_id": proposal_id}
    return {"error": "Proposal not found"}, 404


@app.post("/api/deny/{proposal_id}")
async def deny_proposal(proposal_id: str) -> dict[str, Any]:
    """Deny a pending proposal."""
    global pending_approvals
    approval = None
    for p in pending_approvals:
        if p.get("proposal_id") == proposal_id:
            approval = p
            break
    
    if approval:
        pending_approvals = [p for p in pending_approvals if p.get("proposal_id") != proposal_id]
        # Notify kernel
        if kernel:
            await kernel.event_bus.publish({
                "type": "USER_DENIAL",
                "proposal_id": proposal_id,
                "decision": "denied",
                "timestamp": asyncio.get_event_loop().time()
            })
        return {"status": "denied", "proposal_id": proposal_id}
    return {"error": "Proposal not found"}, 404


# User location state
user_location: dict[str, Any] = {"location": "desk", "at_desk": True}

# Domain approval state - user must approve domains before agents work on them
approved_domains: set[str] = set()  # Empty = all blocked until approved
pending_domain_requests: list[dict[str, Any]] = []


@app.get("/api/user/location")
async def get_user_location() -> dict[str, Any]:
    """Get user's current location in the office."""
    return user_location


@app.post("/api/user/location")
async def set_user_location(request: Request) -> dict[str, Any]:
    """Set user's current location (desk, water_cooler, boardroom)."""
    global user_location
    try:
        body = await request.json()
        location = body.get("location")
    except:
        return {"error": "Invalid JSON"}, 400
    
    valid_locations = ["desk", "water_cooler", "boardroom", "away"]
    if location not in valid_locations:
        return {"error": "Invalid location"}, 400
    
    user_location = {
        "location": location,
        "at_desk": location == "desk",
        "timestamp": asyncio.get_event_loop().time()
    }
    return user_location


# Boardroom meeting requests
meeting_requests: list[dict[str, Any]] = []


@app.get("/api/meetings")
async def get_meeting_requests() -> list[dict[str, Any]]:
    """Get pending meeting requests."""
    return meeting_requests


@app.post("/api/meetings/{session_id}/join")
async def join_meeting(session_id: str) -> dict[str, Any]:
    """Join a boardroom meeting."""
    global meeting_requests
    meeting_requests = [m for m in meeting_requests if m.get("session_id") != session_id]
    
    if kernel:
        await kernel.event_bus.publish({
            "type": "USER_JOINED_MEETING",
            "session_id": session_id,
            "timestamp": asyncio.get_event_loop().time()
        })
    return {"status": "joined", "session_id": session_id}


@app.post("/api/meetings/{session_id}/decline")
async def decline_meeting(session_id: str) -> dict[str, Any]:
    """Decline a boardroom meeting."""
    global meeting_requests
    meeting_requests = [m for m in meeting_requests if m.get("session_id") != session_id]
    
    if kernel:
        await kernel.event_bus.publish({
            "type": "USER_DECLINED_MEETING",
            "session_id": session_id,
            "timestamp": asyncio.get_event_loop().time()
        })
    return {"status": "declined", "session_id": session_id}


# Helper to add approval requests (called by kernel when Chief signs off)
def add_approval_request(proposal_id: str, proposal_data: dict) -> None:
    """Add a proposal for user approval."""
    global pending_approvals
    pending_approvals.append({
        "proposal_id": proposal_id,
        "data": proposal_data,
        "timestamp": asyncio.get_event_loop().time(),
        "status": "pending"
    })


def add_meeting_request(session_id: str, meeting_data: dict) -> None:
    """Add a meeting request for user."""
    global meeting_requests
    meeting_requests.append({
        "session_id": session_id,
        "data": meeting_data,
        "timestamp": asyncio.get_event_loop().time(),
        "status": "pending"
    })


# ── Domain Approval Endpoints ──

@app.get("/api/domains/pending")
async def get_pending_domain_requests() -> list[dict[str, Any]]:
    """Get pending domain approval requests."""
    return pending_domain_requests


@app.get("/api/domains/approved")
async def get_approved_domains() -> list[str]:
    """Get list of approved domains."""
    return list(approved_domains)


@app.post("/api/domains/approve/{domain}")
async def approve_domain(domain: str) -> dict[str, Any]:
    """Approve a domain for agent work."""
    global approved_domains, pending_domain_requests
    
    # Add to approved
    approved_domains.add(domain.lower())
    
    # Remove from pending
    pending_domain_requests = [d for d in pending_domain_requests if d.get("domain") != domain]
    
    # Notify kernel
    if kernel:
        await kernel.event_bus.publish({
            "type": "DOMAIN_APPROVED",
            "domain": domain,
            "timestamp": asyncio.get_event_loop().time()
        })
    
    return {"status": "approved", "domain": domain}


@app.post("/api/domains/deny/{domain}")
async def deny_domain(domain: str) -> dict[str, Any]:
    """Deny a domain request."""
    global pending_domain_requests
    
    pending_domain_requests = [d for d in pending_domain_requests if d.get("domain") != domain]
    
    return {"status": "denied", "domain": domain}


@app.post("/api/domains/approve-all")
async def approve_all_domains() -> dict[str, Any]:
    """Approve all domains."""
    global pending_domain_requests
    
    # Get all unique domains from pending requests
    domains = [d.get("domain") for d in pending_domain_requests]
    approved_domains.update(domains)
    pending_domain_requests = []
    
    return {"status": "approved_all", "domains": domains}


@app.post("/api/domains/pause-all")
async def pause_all_domains() -> dict[str, Any]:
    """Pause all domain scanning - requires approval for new domains."""
    global approved_domains
    approved_domains.clear()
    
    if kernel:
        await kernel.event_bus.publish({
            "type": "DOMAIN_SCANNING_PAUSED",
            "message": "All domain scanning paused - awaiting user approval",
            "timestamp": asyncio.get_event_loop().time()
        })
    
    return {"status": "paused", "message": "All domain scanning paused"}
