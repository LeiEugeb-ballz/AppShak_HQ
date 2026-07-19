# Certification Planning Pack

This folder is planning-only.

For the reconciled repository status, read
[CURRENT_STATUS.md](../../CURRENT_STATUS.md). For all certification and
historical evidence locations, use [docs/INDEX.md](../INDEX.md).

- No tests are implemented here.
- No tests are executed here.
- Purpose: define complete validation and certification structure before running full-system test cycles.

## Files

- `00_certification_scope.md`: frozen constraints, in-scope systems, certification gates.
- `01_repo_test_inventory.md`: current test inventory and ownership by module/layer.
- `02_master_validation_plan.md`: end-to-end validation plan and command sequence (not executed).
- `03_execution_checklists.md`: operator checklists for dry run, execution, and closeout.
- `04_evidence_index_template.md`: artifact and evidence indexing template.
- `05_signoff_template.md`: certification signoff template.
- `06_module_certificate_template.md`: module-level test-state certificate
  template.

## Current State

- Phase 4 operational run evidence exists, but the 6-hour criterion is currently marked partial in `docs/phase_4_operational_validation.md`.
- Full certification should use this pack to rerun and collect complete evidence.

Next: begin with [00_certification_scope.md](00_certification_scope.md), then
[01_repo_test_inventory.md](01_repo_test_inventory.md) and
[02_master_validation_plan.md](02_master_validation_plan.md). Historical
evidence remains under [results/](results/) and [../evidence/phase_2/](../evidence/phase_2/).
