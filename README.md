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
python -m appshak_observability.server --host 127.0.0.1 --port 8010 --mailstore-db appshak_state/substrate/mailstore.db
```

## Phase 3.4 - Projection Semantic Enrichment

Run the projection materializer:

```bash
python -m appshak_projection.run_projector --mailstore-db appshak_state/substrate/mailstore.db --view-path appshak_state/projection/view.json --poll-interval 1
```

Projection view now includes:

- `workers`: per-worker semantic state (`present`, `state`, `last_event_type`, `last_event_at`, `restart_count`, `missed_heartbeat_count`, `last_seen_event_id`)
- `derived`: computed office metadata (`office_mode`, `stress_level`)

## Phase 3.5 - Governance Formalization Layer

Governance logic now lives in `appshak_governance/` and is projection-driven only.

- `AgentRegistry`: versioned agent state (`agent_id`, `role`, `authority_level`, `trust_weights`, `reputation_score`)
- `RelationshipWeightEngine`: deterministic trust/reputation updates from observable outcomes
- `BoardroomArbitrator`: weighted consensus with `decision_score = reasoning_score * authority_level * trust_weight`
- `TrustStabilityMetric`: trust variance over version history

Run governance tests:

```bash
python -m unittest tests.test_governance_layer -v
```

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

## Phase 3 End-to-End Startup

Run each service in a separate terminal from repo root.

1. Swarm runtime:

```bash
python -m appshak_substrate.run_swarm --agents recon forge command --durable --worktrees --duration-seconds 60
```

2. Projection materializer:

```bash
python -m appshak_projection.run_projector --mailstore-db appshak_state/substrate/mailstore.db --view-path appshak_state/projection/view.json --poll-interval 1
```

3. Observability backend:

```bash
python -m appshak_observability.server --host 127.0.0.1 --port 8010 --mailstore-db appshak_state/substrate/mailstore.db
```

4. UI:

```bash
cd appshak-ui
npm install
npm run dev
```

5. Open:

- `http://localhost:5173/#/summary`
- `http://localhost:5173/#/office`

## Ports

- Observability backend: `127.0.0.1:8010`
- UI dev server (Vite): `localhost:5173`
- UI proxy routes: `/api/*`, `/ws/*` -> `127.0.0.1:8010`

## Required Directories

- `appshak_state/substrate/` (durable runtime files)
- `appshak_state/projection/` (projection view store)
- `workspaces/` (when using `--worktrees`)

## Snapshot Contract Sample

`GET /api/snapshot` returns projection view JSON.

```json
{
  "schema_version": 1,
  "timestamp": "2026-03-01T10:58:27.390399+00:00",
  "last_updated_at": "2026-03-01T10:58:27.390399+00:00",
  "running": true,
  "event_queue_size": 21,
  "current_event": {
    "type": "SUPERVISOR_HEARTBEAT",
    "origin_id": "supervisor",
    "timestamp": "2026-03-01T10:58:24.908754+00:00"
  },
  "event_type_counts": {
    "SUPERVISOR_START": 9,
    "SUPERVISOR_STOP": 7
  },
  "tool_audit_counts": {
    "allowed": 1,
    "denied": 0
  },
  "workers": {
    "command": {
      "present": true,
      "state": "ACTIVE",
      "last_event_type": "SUPERVISOR_HEARTBEAT",
      "last_event_at": "2026-03-01T10:58:24.908754+00:00",
      "restart_count": 7,
      "missed_heartbeat_count": 7,
      "last_seen_event_id": 872
    }
  },
  "derived": {
    "office_mode": "RUNNING",
    "stress_level": 0.84
  }
}
```

## Troubleshooting

- `ECONNREFUSED 127.0.0.1:8010` from Vite:
  Observability backend is not running or wrong port. Start backend on `8010`.
- `stream: disconnected` or `SIGNAL LOST` in Office View:
  Ensure both projector and observability backend are running.
- Snapshot appears stale:
  Check projector process and confirm `appshak_state/projection/view.json` timestamp is advancing.
- Worktree errors in swarm startup:
  Ensure repo root has `workspaces/` writable and run with `--worktrees`.

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
