# AppShak Substrate

Durable substrate layer for multi-process AppShak swarms.

## Components

- `mailstore_sqlite.py`: SQLite WAL durable event/mail store with leases + idempotency records.
- `bus_adapter.py`: EventBus-compatible durable adapter (`publish` / `get_next`).
- `supervisor.py`: per-agent worker supervision with heartbeat liveness + bounded restart policy.
- `worker_process.py`: deterministic worker runtime process (`--agent-id/--db-path/--worktree/--consumer-id/--log-path`).
- `workspace_manager.py`: per-agent git worktree isolation.
- `policy.py` + `tool_gateway.py`: strict tool-action enforcement + audit logging + idempotency-key blocking.

## Run Durable Kernel

```bash
python -m appshak_substrate.run_kernel_durable --hours 1 --mailstore-db appshak_state/substrate/mailstore.db
```

## Run Swarm Supervisor

```bash
python -m appshak_substrate.run_swarm --agents recon forge command --durable --worktrees --duration-seconds 120
```

## Run Chambers

```bash
python -m appshak_substrate.chambers.chamber_a_durability
python -m appshak_substrate.chambers.chamber_b_isolation
python -m appshak_substrate.chambers.chamber_c_tool_enforcement
```

Each chamber prints `PASS` or `FAIL` and exits non-zero on failure.

## Run Tests

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```
