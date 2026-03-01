# Phase 3 Projection + Observability + UI Signoff

- Date: 2026-03-01
- Branch: `codex/phase3-finalization-20260301`
- Commit Hash: `0d66b8f`

## Structural Audit

### Projection Layer

- PASS: reads events via `list_events()` and `list_tool_audit()` only.
- PASS: no claim/ack/requeue/fail calls in projector.
- PASS: no direct SQL query strings in projection logic.
- PASS: atomic `view.json` write path uses temporary file + `os.replace`.
- PASS: cursor persistence (`last_seen_event_id`, `last_seen_tool_audit_id`) resumes correctly.

### Observability Backend

- PASS: `GET /api/snapshot` returns projection view JSON.
- PASS: websocket stream emits `view_update` envelopes only.
- PASS: no `appshak_substrate` imports in `appshak_observability/*`.

### UI Boundary

- PASS: projection consumer reads only `/api/snapshot` and `/ws/events`.
- PASS: no direct substrate/supervisor/SQLite imports in UI.
- PASS: animator is delta-driven (`previous` -> `current` diff processing).
- PASS: tab visibility restore resets animator baseline to avoid replay backlog.

## Runtime Validation

Validation artifact:

- `appshak_state/phase3_validation/runtime_validation_summary.json`

Process commands executed:

```bash
python -m appshak_substrate.run_swarm --agents recon forge command --durable --worktrees --duration-seconds 60
python -m appshak_projection.run_projector --mailstore-db appshak_state/substrate/mailstore.db --view-path appshak_state/projection/view.json --poll-interval 1
python -m appshak_observability.server --host 127.0.0.1 --port 8010 --mailstore-db appshak_state/substrate/mailstore.db
```

Runtime checks summary:

- `required_fields_ok: true`
- `running_became_true: true`
- `event_counts_increase_ok: true`
- `workers_update_present: true`
- `process_health_ok: true`
- `runtime_pass: true`

## Snapshot Sample

```json
{
  "schema_version": 1,
  "running": true,
  "event_queue_size": 21,
  "last_seen_event_id": 872,
  "event_type_counts": {
    "SUPERVISOR_HEARTBEAT": 750,
    "WORKER_RESTARTED": 14
  },
  "tool_audit_counts": {
    "allowed": 1,
    "denied": 0
  },
  "workers": {
    "command": {
      "present": true,
      "state": "ACTIVE",
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

## Test Output Excerpt

```text
python -m unittest discover -s tests -p "test_*.py" -v
...
Ran 22 tests in 12.305s
OK
```

## Declaration

- Projection: PASS
- Observability: PASS
- UI Boundary: PASS
- Runtime Validation: PASS
- Tests: PASS

Phase 3 Certification: PASS
