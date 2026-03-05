# Master Validation Plan (Do Not Run Yet)

This is a full validation/certification execution plan.
Status: planning only.

## Phase A - Preflight

1. Confirm branch, clean working tree, and no hidden local mutations.
2. Confirm runtime directories exist and are writable:
   - `appshak_state/substrate`
   - `appshak_state/projection`
   - `appshak_state/inspection`
   - `appshak_state/integrity`
   - `appshak_state/stability`
3. Confirm required ports are free or reserve alternate ports:
   - Observability API: default `8010`
   - UI: default `5173`
4. Confirm external tools available:
   - Python
   - Node/npm
   - Git

## Phase B - Static/Unit Validation

Run once:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Record:

- total tests
- pass/fail
- failure file list (if any)
- rerun result after fixes

## Phase C - Runtime Stack Validation

Start services (separate terminals):

1. Swarm:

```bash
python -m appshak_substrate.run_swarm --agents recon forge command --durable --worktrees --duration-seconds 60
```

2. Projector:

```bash
python -m appshak_projection.run_projector --mailstore-db appshak_state/substrate/mailstore.db --view-path appshak_state/projection/view.json --poll-interval 1
```

3. Observability:

```bash
python -m appshak_observability.server --host 127.0.0.1 --port 8010 --mailstore-db appshak_state/substrate/mailstore.db --projection-view appshak_state/projection/view.json
```

4. UI:

```bash
cd appshak-ui
npm run dev -- --host 127.0.0.1 --port 5173
```

Verify endpoints:

```bash
curl http://127.0.0.1:8010/api/snapshot
curl http://127.0.0.1:8010/api/health
curl http://127.0.0.1:8010/api/inspect/entities
curl http://127.0.0.1:8010/api/integrity/latest
```

## Phase D - Stability and Integrity Validation

Required operational command:

```bash
python -m appshak_stability.run --duration-hours 6
```

Completion criteria:

1. Run status is `completed` (not halted).
2. Multiple checkpoints captured according to cycle policy.
3. No corruption in inspection index artifacts.
4. WebSocket stream uniqueness validated (no duplicate append artifacts).
5. Memory trend does not show sustained growth anomaly.
6. `governance_replay_hash_checkpoint` is populated and stable.
7. Ledger reconstruction hash equality check passes.

## Phase E - Determinism and Replay Validation

1. Recompute integrity/inspection artifacts from same canonical inputs.
2. Compare hash outputs for equality.
3. Validate governance replay/ledger reconstruction hash consistency across checkpoints.

## Phase F - Evidence and Certification

1. Populate evidence index (`04_evidence_index_template.md`).
2. Fill signoff template (`05_signoff_template.md`).
3. Mark each gate pass/fail with explicit artifact links.
4. Publish certification result (PASS only if all required gates pass).
