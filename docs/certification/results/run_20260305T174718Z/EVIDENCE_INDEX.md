# Evidence Index - Run `run_20260305T174718Z`

## Run Metadata

- Run label: `run_20260305T174718Z`
- Date: 2026-03-05
- Type: one-hour stability feedback
- Ports:
  - Observability: `18010`
  - UI: `5174`

## Tested (Executed)

1. Runtime stack launch attempted and observed.
2. API readiness checks and response captures.
3. One-hour stability execution completed.
4. Checkpoint series captured (`12` checkpoints).

## Could Be Tested (Deferred)

1. Full 6-hour stability certification gate.
2. Replay continuity with non-empty governance replay checkpoint.
3. Projection write-path reliability under sustained concurrent runtime.

## Primary Evidence

1. Runner summary:
   - `appshak_state/cert_runs/run_20260305T174718Z/evidence/runner_summary.json`
2. Stability log:
   - `appshak_state/cert_runs/run_20260305T174718Z/evidence/stability_1h.log`
3. Service logs:
   - `appshak_state/cert_runs/run_20260305T174718Z/evidence/swarm.log`
   - `appshak_state/cert_runs/run_20260305T174718Z/evidence/projector.log`
   - `appshak_state/cert_runs/run_20260305T174718Z/evidence/observability.log`
   - `appshak_state/cert_runs/run_20260305T174718Z/evidence/ui.log`
4. API captures:
   - `appshak_state/cert_runs/run_20260305T174718Z/evidence/api_snapshot.json`
   - `appshak_state/cert_runs/run_20260305T174718Z/evidence/api_health.json`
   - `appshak_state/cert_runs/run_20260305T174718Z/evidence/api_entities.json`
   - `appshak_state/cert_runs/run_20260305T174718Z/evidence/api_integrity_latest.json`

## Notable Deviation

- Projector encountered `WinError 5` when replacing projection view file.
- Impact: projection freshness degraded during the run while stability loop still completed.
