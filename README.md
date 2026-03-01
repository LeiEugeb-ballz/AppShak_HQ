# AppShak HQ

Durable substrate + observability stack for multi-process AppShak swarms.

## Components

- `mailstore_sqlite.py`: SQLite WAL durable event/mail store with leases + idempotency records.
- `bus_adapter.py`: EventBus-compatible durable adapter (`publish` / `get_next`).
- `supervisor.py`: per-agent worker supervision with heartbeat liveness + bounded restart policy.
- `worker_process.py`: deterministic worker runtime process (`--agent-id/--db-path/--worktree/--consumer-id/--log-path`).
- `workspace_manager.py`: per-agent git worktree isolation.
- `policy.py` + `tool_gateway.py`: strict tool-action enforcement + audit logging + idempotency-key blocking.

## Phase 1 - Durable Kernel

```bash
python -m appshak_substrate.run_kernel_durable --hours 1 --mailstore-db appshak_state/substrate/mailstore.db
```

## Phase 2 - Swarm Supervisor

```bash
python -m appshak_substrate.run_swarm --agents recon forge command --durable --worktrees --duration-seconds 120
```

## Phase 3.1 - Observability Backend

```bash
python -m appshak_observability.server --mailstore-db appshak_state/substrate/mailstore.db
```

## Phase 3.4 - Projection Semantic Enrichment

Run the projection materializer:

```bash
python -m appshak_projection.run_projector --mailstore-db appshak_state/substrate/mailstore.db --view-path appshak_state/projection/view.json --poll-interval 1
```

Projection view now includes:

- `workers`: per-worker semantic state (`present`, `state`, `last_event_type`, `last_event_at`, `restart_count`, `missed_heartbeat_count`, `last_seen_event_id`)
- `derived`: computed office metadata (`office_mode`, `stress_level`)

## Phase 3.5-3.9 - Governance Cognition Formalization

`appshak_governance/` is projection-driven and deterministic. It does not import substrate, supervisor, or SQLite.

Implemented governance components:

- Agent Registry: `agent_id`, `role`, `authority_level`, `reputation_score`, `trust_weights`, `version`, `last_updated`
- Relationship Weight Engine:
  - deterministic success increase
  - deterministic failure decay
  - escalation penalty
  - bounded trust/reputation values
  - fixed authority scaling bands
- Boardroom Arbitration:
  - `decision_score = reasoning_score * authority_level * trust_weight`
  - static threshold constant: `0.35`
- Water Cooler Propagation:
  - deterministic idle trigger (`office_mode == PAUSED` and `stress_level <= 0.2`)
  - structured lesson schema
  - registry lesson injection + propagation metric
- Trust Stability Metric:
  - rolling variance window (`size=5`)
  - logged only (not used as control input)
- Governance Audit Ledger:
  - immutable append-only log
  - trust changes, arbitration outcomes, registry updates, stability snapshots
  - full registry reconstruction + hash-chain validation
- Deterministic Replay Harness:
  - replay sequence hash equality
  - zero tolerance for variance

Run governance tests:

```bash
python -m unittest tests.test_governance_layer -v
```

## Phase 4 - Integrity + Stability + Inspection (Always-On)

New modules:

- `appshak_integrity/`:
  deterministic integrity reports over projection + governance outputs
- `appshak_stability/`:
  long-duration stability harness with checkpointing (`6h`, `12h`, `24h`)
- `appshak_inspection/`:
  deterministic inspection index for entity/office timelines

Generate an integrity report (default `7d` window):

```bash
python -m appshak_integrity.run_report --window 7d
```

Build inspection index from current projection + governance outputs:

```bash
python -m appshak_inspection.run_index
```

Run stability harness:

```bash
python -m appshak_stability.run --duration-hours 6
python -m appshak_stability.run --duration-hours 12
python -m appshak_stability.run --duration-hours 24
```

Observability inspection APIs:

- `GET /api/inspect/entities`
- `GET /api/inspect/entity/{entity_id}`
- `GET /api/inspect/entity/{entity_id}/timeline?limit=...&cursor=...`
- `GET /api/inspect/office/timeline?limit=...&cursor=...`
- `GET /api/integrity/latest`
- `GET /api/integrity/history?limit=...&cursor=...`
- `GET /api/stability/runs`
- `GET /api/stability/run/{run_id}`
- `GET /api/health`

Observability websocket channels:

- `view_update` (existing)
- `inspect_update`
- `integrity_update`

## Phase 3.2/3.3 - Observability UI (Summary + Office View)

From the repo root:

```bash
cd appshak-ui
npm install
npm run dev
```

Open `http://127.0.0.1:5173` and use the top navigation:

- `Summary View` for dashboard status + event console
- `Office View` for the CCTV-style projection visualization

UI data sources:

- `GET http://127.0.0.1:8010/api/snapshot`
- `ws://127.0.0.1:8010/ws/events`

For local dev with Vite proxy, `/api/*` and `/ws/*` are forwarded to `127.0.0.1:8010`.

## Chambers

```bash
python -m appshak_substrate.chambers.chamber_a_durability
python -m appshak_substrate.chambers.chamber_b_isolation
python -m appshak_substrate.chambers.chamber_c_tool_enforcement
```

Each chamber prints `PASS` or `FAIL` and exits non-zero on failure.

## Tests

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

## Always-On Inspection Runbook

Keep services running in separate terminals and inspect live while tests execute.

Terminal A - swarm runtime:

```bash
python -m appshak_substrate.run_swarm --agents recon forge command --durable --worktrees --duration-seconds 1200
```

Terminal B - projection:

```bash
python -m appshak_projection.run_projector --mailstore-db appshak_state/substrate/mailstore.db --view-path appshak_state/projection/view.json --poll-interval 1
```

Terminal C - integrity report loop (manual cadence):

```bash
python -m appshak_integrity.run_report --window 7d
```

Terminal D - inspection index build loop (manual cadence):

```bash
python -m appshak_inspection.run_index
```

Terminal E - observability backend:

```bash
python -m appshak_observability.server --host 127.0.0.1 --port 8010 --projection-view appshak_state/projection/view.json
```

Terminal F - UI:

```bash
cd appshak-ui
npm install
npm run dev
```

Terminal G - stability harness:

```bash
python -m appshak_stability.run --duration-hours 6
```

Terminal H - tests while dashboard is open:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Open:

- `http://localhost:5173/#/summary`
- `http://localhost:5173/#/office`
