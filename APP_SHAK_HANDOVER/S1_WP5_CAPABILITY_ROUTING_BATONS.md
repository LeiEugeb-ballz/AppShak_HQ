# S1-WP5 — Capability Routing and Verified Batons

Status: `PASS_WITH_NONBLOCKING_FINDINGS` after independent corrective review. This is an uncommitted bounded implementation package; WP6 has not started. The implementation is based on the accepted WP4 checkpoint `BATON-0006` and the current Git basis recorded in `BATON-0007`.

## Canonical baton contract

`VerifiedBatonManager` stores batons in the existing SQLite mailstore. A baton binds its ID, predecessor, owner-task ID, source work package, next objective, canonical repository root, Git commit, working-tree fingerprint, claimed completion state, current state, tests/results, evidence references, persisted validation ID, required capability, creation time, producer, verification state, reason, and verification evidence. `DRAFT`, `VERIFYING`, `VERIFIED`, `REJECTED`, and `SUPERSEDED` are durable states. History is append-only in `baton_history`.

The filesystem JSON under `.appshak/batons/` is a repository-checkpoint handoff projection. It is not trusted or imported automatically and cannot substitute for a SQLite record backed by a real task and validation. Runtime `CURRENT_BATON.json` projections are written only from a verified canonical record. The repository-level `BATON-0007` file remains a pre-checkpoint handover artifact and does not claim runtime dispatchability.

## Verification and lineage

Before verification succeeds, the manager checks that the referenced owner task is `COMPLETE`, the claimed current state matches it, the validation run exists for that task and is persisted `PASSED`, the baton claims `COMPLETE`, the capability is known, the repository identity matches, the recorded commit exists and is the current `HEAD`, the current tracked/untracked working-tree fingerprint matches, every evidence reference resolves inside the repository, and the predecessor is a canonical verified record where one is supplied. Missing, stale, fabricated, escaped, or rejected claims become `REJECTED` and cannot dispatch.

Verification atomically supersedes the predecessor when its successor is accepted. A partial unique constraint and a serialized final lineage check prevent multiple verified successors. Rejected or manually superseded branches cannot dispatch. Filesystem JSON is never auto-promoted to `VERIFIED`.

## Capability contract and routing policy

The supported semantic capabilities are `REPOSITORY_INSPECTION`, `RUNTIME_STABILIZATION`, `IMPLEMENTATION`, `INTEGRATION`, `VALIDATION_IMPLEMENTATION`, `ARCHITECTURAL_AUDIT`, `ROOT_CAUSE_ANALYSIS`, and `CERTIFICATION`. A `CapabilityRoutingPolicy` maps a required capability to enabled configured targets by deterministic `(priority, target_id)` ordering. Worker/model/provider classes live in explicit policy configuration and route output; they are not task or baton truth. An optional requested target is accepted only when that target is explicitly eligible for the capability.

No commercial model is selected by baton data. The source-level default policy contains no invented target and therefore fails closed. A deployment must supply an explicit configured policy. If no eligible configured target exists, routing persists `WAITING_FOR_CAPABILITY` without inventing a target.

## Dispatch and context pack

Only a `VERIFIED` baton can dispatch. Dispatch creates exactly one durable `baton_dispatches` row, bound to the baton and required capability. Repeating dispatch after restart reuses that row and its ID. A dispatch is either `READY_FOR_EXTERNAL_DISPATCH` or `WAITING_FOR_CAPABILITY`; this package does not claim that an external model or Codex desktop session has executed the work.

The deterministic context pack references the baton, predecessor, task, source work package, repository, commit and working-tree basis, validation, test results, evidence, constraints, and distinct next objective. It avoids copying conversation history or the entire repository.

## Files and schema

- `appshak_substrate/schema.sql`: canonical baton, append-only history, and durable dispatch tables.
- `appshak_substrate/mailstore_sqlite.py`: forward migration for reviewed baton-basis/context columns.
- `appshak_substrate/baton_routing.py`: verification, lineage, policy routing, idempotent dispatch, context pack, and projection writer.
- `tests/test_s1_wp5_capability_routing_batons.py`: focused WP5 contract tests.
- `APP_SHAK_HANDOVER/S1_WP5_CAPABILITY_ROUTING_BATONS.md`: this evidence report.
- `.appshak/batons/BATON-0007-s1-wp5.json`: filesystem handoff projection for this package; it is ignored and remains uncommitted in this implementation turn.
- `.appshak/CURRENT_BATON.json`: updated pointer projection; canonical truth remains SQLite.

## Verification results

- Focused WP5 suite after review: **24 passed, 0 failed**.
- Full regression after review: **107 passed, 0 failed**.
- Chambers A, B, and C: **PASS**.
- No production source outside the bounded baton/schema implementation was changed.

## Limitations and next package

External dispatch remains an explicit boundary because this repository has no supported interface for changing a manually selected Codex desktop model. The router records an auditable decision and waits for an eligible configured target; it does not simulate execution. The repository handover JSON and runtime canonical baton are deliberately distinct: a handover file cannot self-promote into SQLite truth. Provider integration, automatic repair, retries, consensus, and WP6 certification remain out of scope.

The next bounded capability is `CERTIFICATION` for WP6, subject to the accepted baton and a fresh verification of the repository state.
