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
