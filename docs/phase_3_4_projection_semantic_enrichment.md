# Phase 3.4 Projection Semantic Enrichment

## Scope

- Extended projection materialized view in `appshak_projection` only.
- Updated projection tests in `tests/test_projection_layer.py`.
- Preserved existing projection keys and read-only behavior.

## New Projection Fields

Projection view adds two top-level keys:

- `workers`: map of `worker_id -> worker_state`
- `derived`: computed metadata for Office View

### Worker State Contract

Each `workers[worker_id]` contains:

- `present` (`bool`)
- `state` (`"IDLE" | "ACTIVE" | "RESTARTING" | "OFFLINE"`)
- `last_event_type` (`str | null`)
- `last_event_at` (`str | null`)
- `restart_count` (`int`)
- `missed_heartbeat_count` (`int`)
- `last_seen_event_id` (`int`)

### Derived Contract

- `office_mode`: `"RUNNING"` if `running=true`, else `"PAUSED"`
- `stress_level`: `min(event_queue_size / 25.0, 1.0)`

## Event Derivation Rules

Worker identifier extraction priority from event payload:

1. `target_agent`
2. `agent_id`
3. `worker`

Worker state transitions:

- `WORKER_STARTED` -> `present=true`, `state=ACTIVE`
- `WORKER_RESTART_SCHEDULED` -> `state=RESTARTING`
- `WORKER_RESTARTED` -> `present=true`, `state=ACTIVE`, `restart_count += 1`
- `WORKER_EXITED` -> `present=false`, `state=OFFLINE`
- `WORKER_HEARTBEAT_MISSED` -> `missed_heartbeat_count += 1`; if `>=2`, `state=OFFLINE`, `present=false`

For worker-targeting events, always update:

- `last_event_type`
- `last_event_at`
- `last_seen_event_id`

## Determinism and Compatibility

- Projection remains read-only (`list_events()` / `list_tool_audit()` only).
- Existing fields remain unchanged.
- New fields normalize safely when absent or malformed.
- No substrate/supervisor/tool-gateway/observability backend changes.

## Run Commands

```bash
# Run projection materializer
python -m appshak_projection.run_projector --mailstore-db appshak_state/substrate/mailstore.db --view-path appshak_state/projection/view.json --poll-interval 1

# Run observability backend
python -m appshak_observability.server --host 127.0.0.1 --port 8010 --mailstore-db appshak_state/substrate/mailstore.db

# Run swarm
python -m appshak_substrate.run_swarm --agents recon forge command --durable --worktrees --duration-seconds 86400

# Run UI
cd appshak-ui
npm run dev

# Run tests
cd ..
python -m unittest discover -s tests -p "test_*.py" -v
```
