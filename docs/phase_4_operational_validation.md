# Phase 4 Operational Validation (Partial Run)

- Date: 2026-03-05
- Branch: `phase4/operational-validation-20260305`
- Validation mode: operational verification only (no architecture/refactor changes)
- Validation status: `PARTIAL` (required 6-hour stability run did not complete)
- Alternate test ports used:
  - Observability API/WebSocket: `127.0.0.1:18010`
  - UI target port reserved: `127.0.0.1:5174` (UI process blocked in this shell; see warnings)

## Required Command

```bash
python -m appshak_stability.run --duration-hours 6
```

Command was executed under active projector + observability services while collecting operational evidence.
The run halted early due to watchdog incident and therefore does not satisfy a completed 6-hour certification run.

## Evidence Artifacts (Committed Location)

Runtime artifacts were archived and committed under:

- `untraacked_20260503/appshak_state/phase4_validation/20260305T055811Z/runner_summary.json`
- `untraacked_20260503/appshak_state/phase4_validation/20260305T055811Z/api_samples.json`
- `untraacked_20260503/appshak_state/phase4_validation/20260305T055811Z/memory_samples.json`
- `untraacked_20260503/appshak_state/phase4_validation/20260305T055811Z/ws_summary.json`
- `untraacked_20260503/appshak_state/stability/run_20260305T055856Z/run_meta.json`
- `untraacked_20260503/appshak_state/stability/run_20260305T055856Z/checkpoints/checkpoint_0003.json`

## Validation Results

1. Dashboard/backend accessibility during run:
   - `/api/health` stayed `status=ok` in all 8 samples.
   - `/api/inspect/entities` returned `entities_count=6` in all 8 samples.
2. Inspection panel data path:
   - Entity inspection API remained responsive during stability execution (`/api/inspect/entities` sampled every cycle).
3. Integrity report regeneration:
   - `last_integrity_report_time` advanced across samples.
   - `last_inspection_index_time` advanced across samples.
4. WebSocket duplication:
   - `message_count=100`
   - `unique_message_count=100`
   - `duplicate_message_count=0`
   - Channels: `view_update=88`, `inspect_update=6`, `integrity_update=6`
5. Memory usage trend (process identifier is environment-specific):
   - 8 samples captured.
   - `working_set_mb` range: `19.023` to `19.070`
   - Trend: stable/slightly decreasing; no growth anomaly observed.
6. Final checkpoint captured:
   - Run: `run_20260305T055856Z`
   - Checkpoint: `checkpoint_0003.json`
   - Actual run window: `2026-03-05T05:58:56.960528+00:00` to `2026-03-05T06:00:57.001347+00:00` (~2 minutes)
   - `ledger_reconstruction_hash_checkpoint=1888baee9e75c995402bb0c318dbef25d4efcdeeed541e0abcb809c33c86f14e`
   - `governance_replay_hash_checkpoint=""`

## Ledger Reconstruction Hash Equality

Verification command (reproducible even if no local ledger file is present):

```python
from pathlib import Path
from appshak_governance.ledger import GovernanceAuditLedger
from appshak_governance.utils import canonical_hash

ledger_path = Path("appshak_state/governance/ledger.jsonl")
ledger = GovernanceAuditLedger(ledger_path)
reconstructed = ledger.reconstruct_registry(fallback_registry={"agents": {}, "history": {}})
assert ledger.validate_hash_chain() is True
assert canonical_hash(reconstructed) == "1888baee9e75c995402bb0c318dbef25d4efcdeeed541e0abcb809c33c86f14e"
print({"ledger_exists": ledger_path.exists()})
```

Result: hash equality confirmed for this run context.
Note: `appshak_state/governance/ledger.jsonl` is runtime-generated and may be absent in a clean checkout.

## Warnings

1. Stability harness halted early by watchdog incident:
   - `type=watchdog_queue_stall`
   - reason: `running=false while queue remains non-zero`
   - impact: 6-hour completion criterion was not met.
2. `governance_replay_hash_checkpoint` remained empty (`""`) for this dataset (stable but unset).
   - impact: governance replay-hash integrity was not validated by this run.
3. UI dev-server process in this shell environment failed with `spawn EPERM` (tooling process spawn restriction), so UI clickability was validated via inspection API availability rather than a live browser session in this run context.

## Outcome

- Operational evidence was collected on alternate ports without architecture changes.
- This document records a partial operational run, not a full 6-hour certification pass.
- Checkpoint, hash equality, websocket dedupe, integrity refresh cadence, and memory stability were documented for the observed window.
