# Execution Checklists (Planning Only)

## Checklist 1 - Pre-Run Control

- [ ] On correct branch.
- [ ] `git status` clean (or explicitly archived runtime artifacts).
- [ ] Required directories present.
- [ ] Port allocation documented (default or alternate).
- [ ] No frozen constraints modified.

## Checklist 2 - Automated Tests

- [ ] Full suite command prepared:
  - `python -m unittest discover -s tests -p "test_*.py" -v`
- [ ] Output capture path prepared.
- [ ] Failure triage template prepared.

## Checklist 3 - Runtime Services

- [ ] Swarm launched and reachable.
- [ ] Projector launched and writing projection snapshots.
- [ ] Observability launched and serving API.
- [ ] UI launched and reachable.
- [ ] Snapshot/inspect/integrity endpoints responding.
- [ ] WebSocket stream observed for update channels.

## Checklist 4 - Stability Run

- [ ] `python -m appshak_stability.run --duration-hours 6` launched.
- [ ] Run reaches planned completion (not halted).
- [ ] Checkpoints collected through end-of-run.
- [ ] Final checkpoint captured.
- [ ] `governance_replay_hash_checkpoint` non-empty.
- [ ] `ledger_reconstruction_hash_checkpoint` verified.

## Checklist 5 - Evidence Integrity

- [ ] Every cited artifact path exists in repository or in declared evidence bundle.
- [ ] Documentation paths match committed paths exactly.
- [ ] Environment-specific values labeled as such (e.g., PIDs).
- [ ] Run ID used as primary stable identifier.

## Checklist 6 - Certification Closeout

- [ ] Signoff template completed.
- [ ] PASS/FAIL stated per criterion.
- [ ] Remaining blockers explicitly listed.
- [ ] Final summary prepared for roadmap continuation.
