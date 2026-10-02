# S1-WP5 Independent Review and Corrective Gate

Review status: `CERTIFIED_WITH_CORRECTIONS`. Starting state: uncommitted candidate implementation at `b5f4634fe12a276e2e60b0a33eec0d13b6d0f06e`, reporting 16 focused tests, 99 full-regression tests, and Chambers A/B/C passing. No candidate work was discarded, and WP6 was not started.

## Invariants reviewed

The review inspected canonical SQLite state, filesystem projection behavior, task/validation completion truth, Git and working-tree basis, evidence confinement, lineage, capability/model separation, successor authority, routing determinism, waiting behavior, verified-only dispatch, idempotency, restart recovery, context sufficiency, external-execution honesty, and WP1–WP4 regression boundaries. Claims were checked against implementation and durable behavior rather than the candidate report or test names.

## Defects found and corrections

1. Verification automatically imported a filesystem JSON predecessor as `VERIFIED` when it contained a PASS-looking string. This allowed JSON to manufacture canonical lineage. Automatic import was removed; a predecessor must already exist as canonical SQLite truth.
2. Multiple successors could verify from the same predecessor. Verification now performs a serialized lineage-head check, enforces one verified successor with a partial unique index, and atomically supersedes the predecessor.
3. The default routing policy invented a placeholder target supporting every capability. The default is now empty and fail-closed; only an explicitly supplied configured policy can yield `READY_FOR_EXTERNAL_DISPATCH`.
4. Git verification bound only `HEAD`, allowing dirty or changed work to pass against the same commit. Batons now persist and verify a deterministic fingerprint of the tracked diff and non-ignored untracked files.
5. Evidence containment was lexical, so `..` or a resolving link could escape the repository. Evidence paths are resolved before containment and existence checks.
6. Claimed current task state was stored but not compared with durable task truth. Verification now rejects a mismatch.
7. Source work package and next objective were conflated, and test/results data was not first-class baton state. Both are now distinct durable fields and are included in the context pack.
8. The original focused suite did not prove rejected-baton non-dispatch, dispatch reuse after reopening, working-tree staleness, JSON non-authority, obsolete-lineage branching, evidence escape, state-claim mismatch, fail-closed default policy, or candidate-schema migration. Focused coverage was extended from 16 to 24 tests.
9. Dispatch verification and insertion were separate transactions without a final status recheck. Dispatch now rechecks that the baton remains the current `VERIFIED` record under the insertion transaction.

## Verdict by contract

Canonical baton, history, and dispatch truth is SQLite-backed. Filesystem records are projections/checkpoint handoffs and cannot auto-verify. COMPLETE requires the real WP4 task and persisted PASS. Commit, working tree, evidence, current task state, capability, and predecessor are verified fail-closed. Capability remains task truth; provider/model classes remain explicit policy metadata. Routing is deterministic, no-target state persists, downstream dispatch is unique per baton, and reopening reuses the durable route/dispatch record. Context contains the source and next-stage references without conversation history. No external model execution is claimed.

The policy abstraction is safe after correction: an explicit policy fixture proves routing mechanics, while the source default contains no synthetic worker. A deployment without configured targets waits.

## Validation

- Focused WP5: 24 passed, 0 failed.
- Full unittest discovery: 107 passed, 0 failed.
- Chamber A: PASS.
- Chamber B: PASS.
- Chamber C: PASS.
- Changed Python files compile; JSON parses; `git diff --check` passes.

## Remaining limitations

The repository has no supported external provider/Codex desktop dispatch interface, so `READY_FOR_EXTERNAL_DISPATCH` is the honest terminal boundary. Concrete deployment targets must be supplied through explicit policy configuration. Repository handover BATON-0007 is not itself a runtime-dispatchable SQLite baton and cannot bypass the task/validation gate. Provider integration, automatic repair, retries, consensus, UI projection, and WP6 certification remain out of scope.

WP5 is safe to checkpoint after the stated final validation. WP6 may proceed only after that separate checkpoint is accepted.
