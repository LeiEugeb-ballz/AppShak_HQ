# S1-WP3 — Durable owner-task contract

Status: PASS_WITH_NONBLOCKING_FINDINGS. Starting commit: `85a10a41490d7a32fbb6721611c63492cc5edc10`. This is a scoped, uncommitted implementation package. S1-WP4 validation has not started.

The repository's existing `.gitignore` ignores `.appshak/`. BATON-0005 exists at the path named below but does not appear in ordinary `git status`; the separate checkpoint operation must explicitly force-stage that single new baton file. No file was staged here.

## Task contract and authority

`owner_tasks` is the authoritative work commitment, independent of mail events and execution attempts. It stores a UUID `task_id`, explicit owner and source request, objective, opaque `authority_id`, state, timestamps, and one durable assignment (agent, workspace identity, assignment authority/source/time). A unique `source_request_id` makes equivalent creation idempotent and rejects conflicting reuse. Creation does not enqueue or execute anything.

Trusted local operator intake is `python -m appshak_substrate.owner_task_cli --db-path <substrate.db> create --owner-id <owner> --objective <text> --authority-id <opaque-id> --source-request-id <stable-key>`. The same module has `assign` and `inspect` commands; `assign --worktree` derives the existing ToolGateway workspace identity. There is no new UI or owner authentication layer. The CLI is a local trusted-operator boundary, not a network authorization service.

Only the task owner may assign the task, using the task's exact authority ID. Assignment is one-time; there is no reassignment or scheduling policy. Task-backed execution remains subject to the existing WP1 ToolGateway authority and workspace checks. The attempt reservation transaction also requires an existing executable task and matching assigned agent, workspace identity, and authority ID. No display label is accepted as task authority. WP1's per-attempt `source_request_id`, operation, timestamp, and Chief authorization still apply; the task ID does not substitute for them.

## Persistence and lifecycle

The existing SQLite substrate has `owner_tasks`, `owner_task_history`, and `owner_task_artifacts`. `execution_attempts.task_id` is nullable so existing non-task-backed WP2 calls continue unchanged. Existing WP2 databases receive an idempotent `ALTER TABLE` migration; no database recreation is required. `owner_task_history` is in the same database and transaction as each authoritative task transition, avoiding a queue message as the sole task record. It records task ID, prior/new state, timestamp, actor/source, and attempt ID when applicable. Artifact rows hold references only, not acceptance verdicts.

State path: `CREATED` → `ASSIGNED` → `EXECUTING` → `READY_FOR_VALIDATION` on durable successful execution. A failed or timed-out attempt yields `EXECUTION_FAILED`. An uncertain attempt or expired running lease yields `NEEDS_RECONCILIATION`. There is no WP3 `COMPLETE` or validation state. No cancellation state was added because no task cancellation operation is implemented.

Task and attempt transitions are transactionally coupled. The store records `task_created`, `task_assigned`, `task_execution_started`, `task_execution_succeeded`, `task_execution_failed`, and `task_needs_reconciliation`. One task may link multiple attempts; it cannot become ready while any linked attempt remains reserved/running. Failure and unknown states are sticky in the absence of an explicit later reconciliation contract. No automatic retry, repair, or replacement attempt is launched. A duplicate source/key replays a known terminal result; a new attempt is denied after failed, unknown, or ready state.

At worker startup, the existing WP2 reconciliation fences expired `RUNNING` attempts and, in the same transaction, moves linked tasks to `NEEDS_RECONCILIATION`. Active attempts remain `EXECUTING`; a recorded successful outcome and its task state cannot disagree because they are committed together. `CREATED`, `ASSIGNED`, and `READY_FOR_VALIDATION` survive reopen without reset. The source-event publication/acknowledgment recovery path remains WP2's existing path.

## Golden workflow

The focused test creates an owner task, assigns it to the existing `command` worker and its temporary worktree, submits one explicit task-backed `TOOL_REQUEST`, starts the real worker process, and writes `golden.txt` with exact known content. The WP2 attempt records `SUCCEEDED`, publication, and acknowledgment. A reopened SQLite store retains the task ID, assignment, linked attempt, artifact path reference, history, and `READY_FOR_VALIDATION`. The content is checked by the test as workflow evidence; WP3 does not persist an acceptance verdict.

## Files changed

- `appshak_substrate/schema.sql`: task, history, artifact-reference tables and fresh-install attempt link.
- `appshak_substrate/mailstore_sqlite.py`: idempotent migration, task creation/assignment/inspection, transactional task/attempt transitions, recovery.
- `appshak_substrate/types.py`, `tool_gateway.py`, `agent_runtime.py`: optional task ID through the authorized request path.
- `appshak_substrate/owner_task_cli.py`: explicit create, assign, inspect entrypoint.
- `tests/test_s1_wp3_durable_owner_task.py`: 14 focused tests.
- `APP_SHAK_HANDOVER/S1_WP3_DURABLE_OWNER_TASK.md`, `.appshak/batons/BATON-0005-s1-wp3.json`, `.appshak/CURRENT_BATON.json`: evidence and handoff.

## Verification

- Focused WP3 suite: 14 passed, 0 failed.
- Full `python -m unittest discover -s tests -p "test_*.py" -v`: 68 passed, 0 failed (54 incoming + 14 WP3).
- Chambers A, B, C: PASS.
- Changed Python files compile; `git diff --check` passes.
- Migration coverage includes a pre-WP3 attempts table with a preserved row and a second reopen. WP1/WP2 suites passed in the full regression.

## Limits and WP4 dependency

The CLI assumes a trusted local operator; it does not authenticate a remote Owner. Authority IDs remain the existing WP1 opaque contract, not a new authority registry. Reassignment, manual reconciliation resolution, retry policy, and task cancellation are intentionally absent. `owner_task_artifacts` records successful `WRITE_FILE` paths, not hashes, content integrity, acceptance criteria, or validated completion. Unknown external effects require investigation; they are never inferred to have failed. WP4 must add persisted artifact binding and validation verdicts before any task can be considered complete.
