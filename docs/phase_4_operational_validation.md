# Phase 4 Operational Validation

- Date: 2026-03-01
- Branch: `phase4/operational-validation-20260301`
- Scope: validation-only (no architecture or runtime behavior changes)

## Command Executed

```bash
python -m appshak_stability.run --duration-hours 6
```

Validation harness artifacts:

- `appshak_state/phase4_validation/20260301T215828Z/runner_summary_v2.json`
- `appshak_state/phase4_validation/20260301T215828Z/api_samples_v2.json`
- `appshak_state/phase4_validation/20260301T215828Z/memory_samples_v2.json`
- `appshak_state/phase4_validation/20260301T215828Z/ws_summary.json`

## Operational Checks

1. Dashboard accessibility:
   - UI endpoint responded during validation window (`http://127.0.0.1:5173/`).
   - Observability health samples stayed `ok` across all 8 checks.
2. Inspection panel data availability:
   - `/api/inspect/entities` returned entity data during run (`entities_count=6` in all samples).
3. Integrity checkpoint regeneration:
   - `last_integrity_report_time` advanced over the validation samples.
   - `last_inspection_index_time` advanced over the validation samples.
4. WebSocket duplication:
   - `message_count=273`, `unique_message_count=273`, `duplicate_message_count=0`.
   - Channel distribution: `view_update=235`, `inspect_update=19`, `integrity_update=19`.
5. Memory trend (stability process):
   - Sample count: 8.
   - Working set MB: `11.086 -> 19.094` during warm-up, then stable at `19.051-19.094`.
   - No sustained upward growth anomaly observed in sampled window.
6. Inspection index integrity:
   - Inspection index remained readable/parseable throughout sampled API checks.
   - No JSON corruption or malformed index artifact observed.

## Final Checkpoint Capture

- Run ID: `run_20260301T220401Z`
- Checkpoint file:
  `appshak_state/stability/run_20260301T220401Z/checkpoints/checkpoint_0003.json`
- Key fields:
  - `ledger_reconstruction_hash_checkpoint`: `1888baee9e75c995402bb0c318dbef25d4efcdeeed541e0abcb809c33c86f14e`
  - `governance_replay_hash_checkpoint`: `""`
  - `watchdog.status`: `incident`
  - `watchdog.reason`: `running=false while queue remains non-zero`

## Ledger Reconstruction Hash Equality

Validation method:

```python
from appshak_governance.ledger import GovernanceAuditLedger
from appshak_governance.utils import canonical_hash

ledger = GovernanceAuditLedger("appshak_state/governance/ledger.jsonl")
reconstructed = ledger.reconstruct_registry(fallback_registry={"agents": {}, "history": {}})
assert canonical_hash(reconstructed) == "1888baee9e75c995402bb0c318dbef25d4efcdeeed541e0abcb809c33c86f14e"
assert ledger.validate_hash_chain() is True
```

Result:

- Reconstructed hash matched checkpoint hash exactly.
- Hash chain validation passed.

## Warnings / Incidents

1. Stability harness halted early by watchdog (`watchdog_queue_stall`) because projection snapshot had:
   - `running=false`
   - `event_queue_size>0`
2. `governance_replay_hash_checkpoint` remained empty in checkpoints (stable but unset in this dataset).

## Outcome

- Operational validation evidence collected.
- Read-only architecture boundaries unchanged.
- No code refactor performed in this step.
