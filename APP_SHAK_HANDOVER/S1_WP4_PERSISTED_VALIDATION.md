# S1-WP4 — Persisted artifact validation

Status: PASS_WITH_NONBLOCKING_FINDINGS. Starting commit: `4852c17146297256c43ae55663113e5e5fcec282`. This is a scoped, uncommitted implementation package. S1-WP5 has not started.

The repository's existing `.gitignore` ignores `.appshak/`. BATON-0006 exists at the path named below but does not appear in ordinary `git status`; the later checkpoint must force-stage only that baton file. No file was staged here.

## Artifact and acceptance contracts

WP3's `owner_task_artifacts` is extended rather than replaced. Each new file artifact has a UUID `artifact_id`, task and producing-attempt IDs, `FILE` kind, canonical location, producer, workspace identity, creation time, byte count, and SHA-256 digest. The row proves what the successful production attempt produced; it does not itself prove acceptance. Existing WP3 artifact rows survive the idempotent migration but lack WP4 integrity fields and are therefore historical references rather than validation-ready records.

`task_acceptance_criteria` persists owner-defined structured checks before execution. Supported deterministic types are `FILE_EXISTS`, `EXACT_TEXT`, and `SHA256`. Each criterion stores its UUID, task, structured JSON configuration, required flag, creator/source, and creation time. Only the task owner can add criteria, and criteria are frozen once execution starts. Display strings such as "approved" or "done" are not criteria.

## Validation lifecycle and completion gate

`validation_runs` and `validation_checks` are distinct from production attempts. A run records task, artifact, validator identity, idempotent source request, state, timestamps, related WP2 validator attempt, validated digest/size, and evidence. Per-criterion rows persist PASS/FAIL and observed evidence. States are `PENDING`, `RUNNING`, `PASSED`, `FAILED`, `ERROR`, and `NEEDS_RECONCILIATION`.

`ArtifactValidator` is the named deterministic capability `system:deterministic-file-validator`. It creates a validation run, then independently reads the produced file through an authorized WP2 `READ_FILE` attempt. The request retains task, authority, source, worker, workspace, operation, validation, and attempt identities. It never trusts the producer's success result or a model statement. A small lease keeper now covers the complete ToolGateway call so process startup/termination cannot exhaust the WP2 fence before its outcome is recorded; existing generation, owner, event-lease, and unknown-outcome checks remain in force.

The task moves `READY_FOR_VALIDATION` → `VALIDATING` when the validator attempt starts. Tool success alone leaves validation `RUNNING`. Completion recomputes the file's current SHA-256 and size inside the persistence gate, requires equality with both the producer artifact record and independently observed bytes, evaluates every required criterion, and persists the result and task transition together. Only all-required checks PASSED plus integrity equality yields validation `PASSED` and task `COMPLETE`. A criterion or integrity mismatch yields `FAILED` and `VALIDATION_FAILED`. Tool/read failure yields `ERROR` and `VALIDATION_ERROR`. An uncertain or expired validator attempt yields `NEEDS_RECONCILIATION`; it is never converted to normal failure or rerun automatically.

Validation history records `task_validation_started`, `task_validation_passed`, `task_validation_failed`, or validation error/reconciliation events. `COMPLETE` remains tied to the persisted validation ID, related read attempt, artifact ID, checked criteria, validated digest, size, and evidence after restart.

## Restart, failure, and repair boundary

Pending validation remains pending. Active validator attempts use WP2 lease/fence truth. Startup reconciliation turns an expired/unknown validator attempt into `NEEDS_RECONCILIATION`; a terminal attempt whose verdict was interrupted becomes `ERROR`, never an inferred pass. Persisted PASS, FAIL, ERROR, and COMPLETE states reopen unchanged. Duplicate validation source submission returns the same terminal run and does not create another attempt.

Failed validation identifies each failed criterion, artifact, observed digest/size, and integrity result. It does not dispatch repair, change assignment, create retry attempts, or invent retry counts. Unknown production tasks cannot create validation runs.

## Golden workflows

PASS: Owner creates a task and exact-text criterion, assigns it, the existing worker performs a real controlled `WRITE_FILE`, and the artifact row captures its path, size, and hash. The deterministic validator performs a separate authorized `READ_FILE`, independently checks exact contents and integrity, persists PASS, and gates the task to COMPLETE. Reopening SQLite preserves the task, assignment, both attempts, artifact, criteria, validation checks, digest evidence, and COMPLETE state.

FAIL: The task expects content A while the worker writes B. Production and artifact persistence succeed, but the independent check persists FAILED and the task becomes VALIDATION_FAILED. Restart preserves the failure and no repair or retry appears.

## Schema and files

- `appshak_substrate/schema.sql`: artifact integrity columns, acceptance criteria, validation runs/checks, and validation-attempt linkage.
- `appshak_substrate/mailstore_sqlite.py`: idempotent WP3 migration, criteria/run APIs, transactional validation states, integrity gate, and restart reconciliation.
- `appshak_substrate/artifact_validator.py`: deterministic validator using ToolGateway READ_FILE.
- `appshak_substrate/types.py`, `tool_gateway.py`, `agent_runtime.py`: optional validation ID and durable authorized validation attempt path.
- `tests/test_s1_wp4_persisted_validation.py`: 15 focused tests covering all requested WP4 scenarios before the full-regression gate.
- `APP_SHAK_HANDOVER/S1_WP4_PERSISTED_VALIDATION.md`, `.appshak/batons/BATON-0006-s1-wp4.json`, `.appshak/CURRENT_BATON.json`: evidence and handoff.

## Verification

- Focused WP4: 15 passed, 0 failed.
- WP2 recovery regression after lease-coverage hardening: 12 passed, 0 failed.
- Full `python -m unittest discover -s tests -p "test_*.py" -v`: 83 passed, 0 failed (68 incoming + 15 WP4).
- Chambers A, B, and C: PASS.
- Changed Python files compile and `git diff --check` passes.
- Fresh schema, WP3-format migration, and repeated reopen are covered.

One earlier full-suite run exposed the accepted WP2 short-lease race during Windows process cleanup; after extending renewal over the entire ToolGateway call, the focused WP2 suite and final full suite pass. This is a fence-preserving reliability correction, not a retry or authority bypass.

## Limits and WP5 dependency

WP4 validates UTF-8 file artifacts only. It is not a general artifact registry or CI system. Legacy WP3 artifact rows are preserved but lack sufficient integrity metadata for validation. The persisted digest proves which version completed; later external mutation does not rewrite that evidence, but WP4 does not continuously monitor files or automatically demote a completed task. Owner intake remains a trusted local API/CLI boundary. There is no automatic repair, retry, validator consensus, model selection, routing, baton dispatch, or UI projection.

WP5 may route configured capabilities and export verified batons only from canonical task/validation truth. It must require the persisted PASSED validation and integrity binding established here; conversation claims, tool success, and mere artifact existence remain insufficient.
