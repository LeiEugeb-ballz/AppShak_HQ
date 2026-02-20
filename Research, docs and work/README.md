# AppShak - Self-Evolving Cognitive Multi-Agent System

AppShak is a self-evolving cognitive organism composed of autonomous agents that work together to identify real-world problems, construct solutions, and continuously improve their own capabilities.

## Quick Launch (Recommended for Observers/Builders/QC Agents)

For easy access, use the interactive launcher:

```bash
python launcher.py
```

This provides a menu-driven interface with shortcuts for all environments.

## Three Versions

This project offers three different deployment variants:

| Version | Description | Use Case |
|---------|-------------|----------|
| **Original** (`appshak/`) | Core library - Python API for programmatic use | Integration into other Python projects |
| **Live** (`appshak_live/`) | WebUI version with real-time dashboard | Visual monitoring and web-based interaction |
| **Office** (`appshak_office/`) | Office metaphor with Water Cooler & Boardroom | Advanced collaboration with office-inspired UI |

---

## 1. Original AppShak (Core Library)

The original version is a Python library that provides the core kernel and agents for programmatic use.

### Features

- **Three Specialized Agents:**
  - [`ScoutAgent`](appshak/agents/scout.py) - Reconnaissance and problem discovery
  - [`BuilderAgent`](appshak/agents/builder.py) - Solution construction and execution
  - [`ChiefAgent`](appshak/agents/chief.py) - Decision making and coordination
- **Event-driven architecture** via [`EventBus`](appshak/event_bus.py)
- **Global memory system** for persistent state ([`GlobalMemory`](appshak/memory.py))
- **Safeguard monitoring** for constitutional compliance ([`SafeguardMonitor`](appshak/safeguards.py))

### Setup

```bash
# No external dependencies required (uses Python standard library)
cd c:/Users/Me/Desktop/AppShak_HQ
```

### Running

Import and use the kernel in your Python code:

```python
import asyncio
from appshak import AppShakKernel

async def main():
    config = {
        "heartbeat_interval": 15,
        "event_poll_timeout": 1.0,
    }
    
    kernel = AppShakKernel(config)
    await kernel.start()
    
    # Your application logic here
    # The kernel will run the agent loop
    
    await kernel.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
```

### Running as a Script

Create a file `run_appshak.py`:

```python
import asyncio
import sys
sys.path.insert(0, "c:/Users/Me/Desktop/AppShak_HQ")

from appshak import AppShakKernel

async def main():
    config = {
        "heartbeat_interval": 15,
        "event_poll_timeout": 1.0,
    }
    
    kernel = AppShakKernel(config)
    
    print("Starting AppShak Kernel...")
    await kernel.start()
    print("AppShak Kernel started successfully!")
    print("Press Ctrl+C to stop...")
    
    try:
        while kernel.running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        await kernel.shutdown()
        print("AppShak Kernel stopped.")

if __name__ == "__main__":
    asyncio.run(main())
```

Then run:
```bash
python run_appshak.py
```

---

## 2. AppShak Live (WebUI Version)

The Live version provides a web-based dashboard with real-time event streaming via WebSockets.

### Features

- **Real-time Dashboard** - Visual interface showing agent activities
- **WebSocket Event Stream** - Live updates of all system events
- **FastAPI Backend** - RESTful API for metrics and control
- **Three Agents:** Scout, Builder, Chief (same as original)
- **Safeguard Monitoring** - Constitutional compliance checking

### Requirements

```text
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
websockets>=12.0
```

### Setup

```bash
cd c:/Users/Me/Desktop/AppShak_HQ/appshak_live

# Create and activate virtual environment (recommended)
python -m venv venv
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### Running

```bash
# Run with uvicorn
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

Or programmatically:

```python
import uvicorn

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
```

### Accessing

Open your browser and navigate to:
- **Dashboard:** http://localhost:8000/
- **API Docs:** http://localhost:8000/docs

### Configuration

Edit the `KERNEL_CONFIG` in [`server.py`](appshak_live/server.py:15):

```python
KERNEL_CONFIG = {
    "heartbeat_interval": 4,        # Heartbeat interval in seconds
    "event_poll_timeout": 1.0,       # Event polling timeout
    "safeguard_retry_max": 3,        # Max safeguard retries
    "safeguard_cooldown_seconds": 30, # Safeguard cooldown period
    "endpoint_whitelist": [          # Allowed external endpoints
        "https://api.appshak.io/v1/deploy",
        "https://api.appshak.io/v1/analyze",
        "https://api.appshak.io/v1/monitor",
        "https://api.appshak.io/v1/predict",
    ],
}
```

---

## 3. AppShak Office (Advanced Collaboration)

The Office version implements an "office metaphor" for agent collaboration with unique features like Water Cooler conversations and Boardroom meetings.

### Features

- **Agent Desks** - Each agent has a dedicated workspace
- **Water Cooler** - Random idle agent pairs sharing summaries/questions (every 1-2 minutes)
- **Boardroom** - All agents come together for project discussions and launches
- **Organizational Memory** - Persistent memory with JSON storage
- **Enhanced Metrics** - Detailed metrics API endpoint

### Requirements

```text
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
websockets>=12.0
```

### Setup

```bash
cd c:/Users/Me/Desktop/AppShak_HQ/appshak_office

# Create and activate virtual environment (recommended)
python -m venv venv
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r ../appshak_live/requirements.txt

# Ensure storage directory exists
mkdir appshak_office_state
```

### Running

```bash
# Run with uvicorn
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

Or programmatically:

```python
import uvicorn

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8001, reload=True)
```

### Accessing

Open your browser and navigate to:
- **Dashboard:** http://localhost:8001/
- **Metrics API:** http://localhost:8001/api/metrics
- **API Docs:** http://localhost:8001/docs

> Note: Office runs on port 8001 to avoid conflicts with Live version on port 8000.

### Configuration

Edit the `KERNEL_CONFIG` in [`server.py`](appshak_office/server.py:15):

```python
KERNEL_CONFIG = {
    "heartbeat_interval": 10,        # Heartbeat interval in seconds
    "event_poll_timeout": 1.0,       # Event polling timeout
    "storage_root": "appshak_office_state",  # Memory storage directory
}
```

### Office-Specific Features

#### Water Cooler
The Water Cooler feature (`appshak_office/office.py:21`) enables random agent interactions:
- Activates every 1-2 minutes after system stability
- Randomly pairs idle agents to share summaries and questions
- Fosters emergent collaboration

#### Boardroom
The Boardroom feature (`appshak_office/office.py:100`) brings all agents together:
- Scheduled discussions for project reviews
- Launch planning for new initiatives
- Skills upgrading sessions

---

## Quick Start Commands

### Running All Versions

```bash
# Terminal 1 - Original (Core)
cd c:/Users/Me/Desktop/AppShak_HQ
python run_appshak.py

# Terminal 2 - Live (WebUI)
cd c:/Users/Me/Desktop/AppShak_HQ/appshak_live
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8000

# Terminal 3 - Office
cd c:/Users/Me/Desktop/AppShak_HQ/appshak_office
pip install -r ../appshak_live/requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      AppShak Kernel                         │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Scout     │  │   Builder   │  │       Chief         │ │
│  │  (Recon)    │──│   (Forge)   │──│     (Command)       │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│         │                │                    │            │
│         └────────────────┼────────────────────┘            │
│                          ▼                                   │
│                 ┌──────────────┐                             │
│                 │  Event Bus   │                             │
│                 └──────────────┘                             │
│                          │                                   │
│         ┌────────────────┼────────────────┐                  │
│         ▼                ▼                ▼                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │   Memory    │  │ Safeguards │  │  Metrics    │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

### Version-Specific Additions

| Component | Original | Live | Office |
|-----------|----------|------|--------|
| Kernel | ✅ | ✅ (with metrics) | ✅ (OfficeKernel) |
| Agents | ✅ | ✅ | ✅ (enhanced) |
| Event Bus | ✅ | ✅ (broadcasts) | ✅ (enhanced) |
| Memory | GlobalMemory | - | OrganizationalMemory |
| Dashboard | - | ✅ | ✅ (Office-themed) |
| Water Cooler | - | - | ✅ |
| Boardroom | - | - | ✅ |

---

## Troubleshooting

### Port Already in Use

If you get `Address already in use` errors:
- Live: Use `--port 8002` or any available port
- Office: Default port is 8001

### Import Errors

Ensure you're running from the correct directory:
```bash
cd c:/Users/Me/Desktop/AppShak_HQ
python -c "from appshak import AppShakKernel"  # For original
```

### Virtual Environment Issues

Windows:
```bash
venv\Scripts\activate
```

Linux/Mac:
```bash
source venv/bin/activate
```

---

## File Structure

```
AppShak_HQ/
├── launcher.py                 # Interactive launcher (recommended)
├── README.md                   # This file
├── appshak/                    # Original Core Library
│   ├── __init__.py
│   ├── kernel.py              # AppShakKernel
│   ├── event_bus.py          # Event-driven communication
│   ├── memory.py             # GlobalMemory
│   ├── safeguards.py         # SafeguardMonitor
│   └── agents/
│       ├── base.py
│       ├── scout.py          # ScoutAgent
│       ├── builder.py        # BuilderAgent
│       └── chief.py          # ChiefAgent
│
├── appshak_live/              # WebUI Version
│   ├── __init__.py
│   ├── kernel.py             # AppShakKernel (with metrics)
│   ├── server.py             # FastAPI server
│   ├── dashboard.html        # Real-time dashboard
│   ├── agents.py
│   ├── event_bus.py
│   ├── safeguards.py
│   └── requirements.txt
│
├── appshak_office/            # Office Version
│   ├── __init__.py
│   ├── kernel.py             # OfficeKernel
│   ├── office.py             # WaterCooler & Boardroom
│   ├── server.py             # FastAPI server
│   ├── dashboard.html        # Office dashboard
│   ├── agents.py
│   ├── event_bus.py
│   ├── memory.py             # OrganizationalMemory
│   └── server.py
│
└── appshak_office_state/      # Office memory storage
```

---

## License

This is part of the AppShak Organization's cognitive multi-agent system implementation.
