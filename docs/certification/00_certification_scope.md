# Certification Scope and Constraints

## Objective

Define the complete validation perimeter for AppShak certification without changing runtime architecture or frozen controls.

## Frozen Constraints (Must Not Change During Certification)

- Substrate runtime behavior, supervisor behavior, worker runtime behavior.
- PM v1 baseline constants and metric definitions.
- Projection read-only contract (no claim/ack/requeue/fail).
- Observability read-only boundary (no substrate direct access).
- UI read-only behavior.
- Governance constants/math from Phase 3 baseline.

## Layers in Scope

1. `appshak_substrate/`
2. `appshak_plugins/`
3. `appshak_projection/`
4. `appshak_governance/`
5. `appshak_integrity/`
6. `appshak_inspection/`
7. `appshak_stability/`
8. `appshak_observability/`
9. `appshak-ui/`
10. `appshak_dashboard/` (legacy/read-only surface where applicable)

## Certification Exit Criteria (All Required)

1. Unit/integration test suite passes.
2. Runtime validation sequence passes with required durations and checkpoints.
3. Determinism checks pass (replay/hash equality where specified).
4. Boundary checks pass (forbidden imports and no upward coupling).
5. Evidence artifacts stored and indexed for reproducibility.
6. Signoff document completed with PASS/FAIL by criterion.

## Explicit Non-Goals for This Planning Pack

- No code refactor.
- No test implementation.
- No test execution.
- No production deployment actions.
