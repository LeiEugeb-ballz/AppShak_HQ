# AppShak HQ — Current Status

This is the canonical factual status snapshot for the repository. It links to
the underlying records rather than replacing them.

For setup and navigation, start with [README.md](README.md) and
[docs/INDEX.md](docs/INDEX.md).

## Current development position

- The current `main` commit at the time this document was prepared is
  `cd8a3dc3e6d1486a7a95afa29b61aa88f8cfcd43` (2026-04-26), titled
  `Phase 2 stabilization patch: memory determinism, event purity, vault isolation`.
- The active source tree includes Phase 4 runtime, pipeline, writer, and
  evaluation modules in `appshak_phase4/`.
- The repository contains the `phase-4-certified` tag on an earlier commit and
  a Phase 4 evaluation summary dated 2026-04-18 that records `Status: PASS` for
  its bounded pipeline run.
- Earlier onboarding and contribution documents described Phase 3B
  certification as the active working boundary. Those statements are retained
  as the policy context for Phase 3B work; they are not the authoritative
  repository-wide maturity summary.

## Completed and recorded phases

| Area | Recorded status | Evidence |
|---|---|---|
| Phase 2 substrate | Signed as certified on 2026-02-25. | [Phase 2 Substrate Signoff](docs/phase_2_substrate_signoff.md) and [Phase 2 evidence](docs/evidence/phase_2/). |
| Phase 3 projection | Projection semantic-enrichment contract recorded. | [Phase 3.4 Projection Record](docs/phase_3_4_projection_semantic_enrichment.md) |
| Phase 3 governance | Governance formalization recorded as complete. | [Phase 3 Governance Record](docs/phase_3_governance_complete.md) |
| Phase 4 design | Integrity and recursive self-observation scope recorded. | [Phase 4 Design Record](docs/phase_4_integrity_self_observation.md) |
| Phase 4 operational run | A 2026-03-05 operational run is explicitly recorded as partial. | [Operational Validation](docs/phase_4_operational_validation.md) |
| Phase 4 evaluation | A 2026-04-18 pipeline evaluation records deterministic replay equality and `Status: PASS`. | [Evaluation Summary](docs/phase4/PHASE4_EVAL_SUMMARY.md) |

## Certification position

The certification record is intentionally preserved as multiple scoped pieces
of evidence rather than one inferred verdict.

- The Phase 2 substrate signoff records direct chamber, crash-recovery,
  worktree-isolation, tool-gateway, idempotency, and unit-test evidence.
- The Phase 4 operational-validation document states that its required six-hour
  stability run halted early; that document is a **partial-run record**, not a
  full six-hour certification pass.
- The Phase 4 evaluation summary records a later bounded pipeline evaluation
  with passing replay and integrity checks. It does not state that it replaces
  the partial six-hour operational-validation record.
- The planning pack in `docs/certification/` remains the repository’s complete
  validation and evidence-collection structure.

## Documented active work and priorities

No tracked issue tracker, owner assignment, or current task list was found in
the repository documentation. The currently documented verification priorities
are therefore the items explicitly left incomplete by existing evidence:

1. Complete the six-hour stability criterion described in
   [Phase 4 Operational Validation](docs/phase_4_operational_validation.md).
2. Capture a non-empty governance replay-hash checkpoint for that run scope.
3. Use the existing [Certification Planning Pack](docs/certification/README.md)
   to index evidence and record any subsequent signoff.

This list reports prior documentation findings; it is not a new roadmap.

## Repository health and dependency record

- Active Python source, tests, UI, and documentation are present in the
  repository root.
- No root `pyproject.toml`, `setup.py`, `setup.cfg`, or active
  `requirements.txt` is tracked.
- [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md) is the canonical documentation
  of the currently stated installation dependencies. It is not a package lock
  or a replacement for a future dependency manifest.
- `appshak_state/` is ignored runtime output. Preserved historical runtime
  evidence exists separately under `untraacked_20260503/`.

## Read next

- [Repository and Documentation Navigator](docs/INDEX.md)
- [Environment Setup](ENVIRONMENT_SETUP.md)
- [Developer Onboarding](ONBOARDING.md)
- [Contributing Guide](CONTRIBUTING.md)
