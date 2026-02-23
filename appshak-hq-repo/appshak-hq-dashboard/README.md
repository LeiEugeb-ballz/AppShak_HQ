# 👑 AppShak HQ — Cognitive Organism Command Center

> **A real-time 3D CCTV surveillance dashboard for a self-evolving multi-agent AI system.**  
> Built with Three.js · Vanilla JS · Share Tech Mono · Orbitron

![AppShak HQ Preview](docs/preview.png)

---

## What Is This?

AppShak HQ is the operator interface for **AppShak** — a Cognitive Organism architecture where autonomous AI agents (Scout, Builder, Chief) collaborate to discover, build, and deploy software products with minimal human intervention.

This dashboard gives the **Boss** a live 3D CCTV view into the agent office, with full approval authority over builds and boardroom sessions.

---

## Architecture

```
AppShak Cognitive Organism
│
├── 🔍 SCOUT      — Fast/Divergent · Llama 8B
│   └── Scans domains, scores viability, queues proposals
│
├── 🔧 BUILDER    — Precise/Coder · Mid-weight
│   └── Scaffolds solutions in isolated git worktrees
│
├── 👑 CHIEF      — Strategic Arbiter · 70B+
│   └── Convenes board, enforces constitutional rules
│
└── 👔 BOSS (YOU) — Final approval authority
    └── Approves/denies builds, reviews policy blocks
```

### The Closed Loop of Autonomy

```
FIND → APPROVE → EXECUTE → VALIDATE → LEARN → UPDATE → (repeat)
```

Each stage drives agent movement, zone lighting, and live event feed entries in the dashboard.

---

## Features

| Feature | Description |
|---|---|
| **3D CCTV View** | Corner-mounted camera, orbit freely with mouse |
| **Boss Approval Toggle** | Gate every boardroom session and build |
| **Live Event Feed** | Fully descriptive, colour-coded event stream |
| **Virtual Boss Desk** | Three paper piles: Policy Blocks, Board Reports, Adhoc Queries |
| **Agent Skill Profiles** | Init skills, self-acquired, peer-sourced at Water Cooler |
| **Water Cooler Archive** | Timestamped knowledge exchange log |
| **Theme Switcher** | Default · Cyber · Heat · Ice · Ghost · Military |
| **Boardroom Notifications** | Join/Approve/Deny with one click |
| **Build Approval Notifications** | Sign off on deploys before they go live |
| **Footer Stat Dropdowns** | Clickable — switch loop stage or agent confidence live |
| **OrbitControls** | Left-drag to rotate · Scroll to zoom · Right-drag to pan |

---

## Quick Start

### Option 1 — Just open the file
```bash
git clone https://github.com/YOUR_USERNAME/appshak-hq.git
cd appshak-hq
open index.html   # macOS
# or
xdg-open index.html  # Linux
```
No build step. No dependencies to install. Pure HTML/JS.

### Option 2 — Serve locally (recommended for WS integration)
```bash
cd appshak-hq
python3 -m http.server 8080
# then open http://localhost:8080
```

---

## Connecting to Your Live Backend

The entire simulation loop is currently driven by `setInterval`. To wire it to your real AppShak backend:

**1. Find the main loop** (`advanceStage` function) and replace with WebSocket:

```javascript
// Replace setInterval with:
const ws = new WebSocket('ws://localhost:8765');

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  handleBackendEvent(msg.type, msg.payload);
};

function handleBackendEvent(type, payload) {
  // Map your backend event types to UI stage changes
  const stageMap = {
    'SCOUT_SCAN':        0,
    'BOARDROOM_CONVENE': 1,
    'TASK_ASSIGNED':     2,
    'QA_RUNNING':        3,
    'WATER_COOLER_START':4,
    'MEMORY_UPDATE':     5,
  };
  if (stageMap[type] !== undefined) {
    stageIdx = stageMap[type];
    applyStagePositions(LOOP_STAGES[stageIdx]);
    renderAll();
  }
  // Push to live feed
  pushFeed(type.toLowerCase().split('_')[0], `[${type}]`, JSON.stringify(payload));
}
```

**2. Backend event types expected:**

| Event | Trigger |
|---|---|
| `SCOUT_SCAN` | Scout begins domain scan |
| `BOARDROOM_CONVENE` | Chief calls meeting |
| `BOARDROOM_ADJOURN` | Meeting ends |
| `TASK_ASSIGNED` | Builder gets approved task |
| `QA_RUNNING` | Validation suite starts |
| `WATER_COOLER_START` | Agent knowledge exchange begins |
| `WATER_COOLER_END` | Session closes |
| `MEMORY_UPDATE` | Chief writes to vector store |
| `POLICY_BLOCK` | Constitutional invariant enforced |
| `PROPOSAL_DECISION` | Board decision logged |

---

## File Structure

```
appshak-hq/
│
├── index.html          ← The entire dashboard (self-contained)
├── README.md           ← This file
├── .gitignore
│
├── docs/
│   ├── ARCHITECTURE.md ← Cognitive Organism design doc
│   └── preview.png     ← Screenshot for README
│
└── src/                ← Future: split JS/CSS modules
    └── .gitkeep
```

---

## Roadmap

- [ ] WebSocket integration to live Python backend
- [ ] Real raycasting click detection (replace screen-coord approximation)
- [ ] Agent pathfinding around furniture obstacles
- [ ] Agent name labels floating in 3D space (CSS2DRenderer)
- [ ] Sound design — ambient office hum, notification chimes
- [ ] Mobile touch controls
- [ ] Replay mode — scrub through past cycles
- [ ] Export session log as JSON

---

## The Constitution (Article 0)

> *The Prime Directive is non-terminal self-improvement. No agent may act outside the EventBus. All builds require operator sign-off. The Chief holds veto authority. Memory is persistent and cumulative.*

---

## License

MIT — built for AppShak by the Cognitive Organism team.
