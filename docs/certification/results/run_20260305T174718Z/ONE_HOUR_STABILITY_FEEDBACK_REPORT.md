# One-Hour Stability Feedback Report

- Run ID: `run_20260305T174718Z`
- Date: 2026-03-05
- Mode: development feedback run (not final production certification)

## Executed

1. Runtime stack launch on alternate ports:
   - Observability: `127.0.0.1:18010`
   - UI: `127.0.0.1:5174`
2. API readiness and capture:
   - `/api/health`
   - `/api/snapshot`
   - `/api/inspect/entities`
   - `/api/integrity/latest`
3. One-hour stability run:
   - `python -m appshak_stability.run --duration-hours 1`

## Outcome Summary

1. Stability run completed:
   - Stability run id: `run_20260305T174810Z`
   - `run_meta.status`: `completed`
   - `checkpoint_count`: `12`
   - `incident`: `null`
2. UI/API reachability passed:
   - UI HTTP status: `200`
   - API health status: `ok`
3. Known caveat:
   - Projector failed early with `PermissionError [WinError 5]` when atomically replacing `appshak_state/projection/view.json`.
   - Projection timestamp remained stale for much of the one-hour window.

## Certification Interpretation

1. Deferred items partially reduced:
   - Runtime stack launch commands: exercised.
   - Long-run stability: exercised at 1h only.
2. Deferred items still open:
   - Full 6-hour production gate.
   - Replay/hash continuity gate with non-empty `governance_replay_hash_checkpoint`.
   - Projection freshness under lock-free stable write conditions.

## Evidence Paths

- `appshak_state/cert_runs/run_20260305T174718Z/evidence/runner_summary.json`
- `appshak_state/cert_runs/run_20260305T174718Z/evidence/stability_1h.log`
- `appshak_state/cert_runs/run_20260305T174718Z/evidence/projector.log`
- `appshak_state/cert_runs/run_20260305T174718Z/evidence/observability.log`
- `appshak_state/cert_runs/run_20260305T174718Z/evidence/ui.log`
- `appshak_state/cert_runs/run_20260305T174718Z/evidence/api_snapshot.json`
- `appshak_state/cert_runs/run_20260305T174718Z/evidence/api_health.json`
- `appshak_state/cert_runs/run_20260305T174718Z/evidence/api_entities.json`
- `appshak_state/cert_runs/run_20260305T174718Z/evidence/api_integrity_latest.json`
