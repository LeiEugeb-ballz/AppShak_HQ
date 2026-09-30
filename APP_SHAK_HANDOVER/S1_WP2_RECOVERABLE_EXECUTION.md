# S1-WP2 Recoverable Execution

Status: **PASS_WITH_NONBLOCKING_FINDINGS**  
Work package: S1-WP2 — Make execution attempts recoverable  
Starting commit: `ce131005e6a47f84b0952fbc57d5bd6682478ba8`  
Repository: `E:\AppShak_HQ`

## Original crash windows

The durable request was claimed in `SQLiteMailStore`, but `ToolGateway.execute` reserved an idempotency key, ran the tool, wrote the key result, and appended audit in separate operations. `AgentRuntime` then published a result, and `worker_process` acknowledged the source event separately. A crash between any two steps could strand an unexecuted reservation, lose a completed effect's outcome, duplicate a result event, or redeliver an already completed request. The old `allow_duplicate` flag bypassed the key reservation. A synchronous tool also blocked worker heartbeat and allowed the source event lease to expire.

## Execution path and lifecycle

`SQLiteMailStore.claim_next_event` supplies the durable event and source lease. `worker_process._main` gives it to `AgentRuntime.handle_event`, which propagates the WP1 authority contract to `ToolGateway.execute`. The gateway validates authority and policy, then atomically reserves an `execution_attempts` row and its existing `idempotency_keys` row. An attempt receives a UUID, source request/event references, authority, worker, workspace, operation, idempotency key, creation time, and normalized request contract.

The states are `RESERVED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `TIMED_OUT`, and `NEEDS_RECONCILIATION`:

1. `RESERVED` has no proven side effect and may be started after redelivery.
2. `RUNNING` has an owner, monotonic generation, expiry, and start time. Only one owner can start it.
3. A fenced outcome transaction writes state, outcome, tool audit, and idempotency result together.
4. Result publication inserts one `TOOL_RESULT` event and sets `published_event_id` in one transaction.
5. Source acknowledgment updates the source event and `acknowledged_at` in one transaction.

The external effect cannot be included in the SQLite transaction. A crash after an effect starts but before outcome persistence becomes `NEEDS_RECONCILIATION` after lease expiry. It is never automatically replayed as a fresh effect.

## Idempotency and duplicate delivery

`source_request_id` and `idempotency_key` are unique in `execution_attempts`. A duplicate with a different normalized request or authority contract is denied. A matching duplicate while `RUNNING` cannot start another execution. A matching duplicate after a durable terminal outcome returns the stored result and audit reference. An unstarted `RESERVED` attempt can continue. `allow_duplicate` is denied. A durable `FAILED` result remains failed; there is no implicit retry because this layer has no configured failure retry policy. Existing legacy keys without attempt records are refused for manual reconciliation.

## Leases and fencing

Each start increments the attempt generation. Renewal and outcome recording require the current owner, generation, unexpired attempt lease, and, for durable source events, the matching unexpired source event lease. The worker renews its event lease and heartbeat during a tool call. The gateway renews the execution lease while a subprocess runs. Both intervals derive from the configured lease duration. An expired `RUNNING` attempt is fenced by incrementing its generation and becomes `NEEDS_RECONCILIATION`; expiry does not authorize re-execution.

The supervisor now uses a UUID in each consumer ID, preventing old and replacement workers from sharing an owner label. A stale worker cannot record authoritative success after either fence is lost.

## Timeout and process tree

Subprocess tools use `Popen` with periodic lease checks and a monotonic timeout. A timeout is recorded as `TIMED_OUT`, never success. On Windows, the launched process is assigned to a Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`; closing the worker's handle terminates associated descendants, including after worker crash. Timeout also invokes `taskkill /T /F`. If Windows process-tree protection or termination cannot be established, the gateway treats the outcome as uncertain. On other platforms, the process starts in a new session and the process group is terminated. These Windows behaviors follow Microsoft's [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects), [AssignProcessToJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject), and [limit flag](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information) documentation.

Supervisor initiated worker termination also targets the Windows process tree. The tests verify a timed-out child and a child of a crashed worker do not continue to their delayed side effect.

## Restart reconciliation

At worker startup, `reconcile_attempts` leaves `RESERVED` and currently leased `RUNNING` attempts intact, and fences expired `RUNNING` attempts as `NEEDS_RECONCILIATION`. Recorded outcomes awaiting publication are published from the stored outcome. Published outcomes awaiting acknowledgment are acknowledged when no other valid source lease owns the event. Redelivery follows the same stored attempt rather than re-running an effect. Unknown attempts retain their original authority fields and require external investigation; this package does not invent a success verdict or a replacement authority.

## Schema and migration

`schema.sql` adds an `execution_attempts` table and state/lease index. The existing database remains in place. `CREATE TABLE/INDEX IF NOT EXISTS` runs on fresh and existing SQLite databases and preserves prior events, audit, idempotency records, and heartbeats. A migration test creates a pre-WP2 schema with durable rows and opens it twice with the new store. Old idempotency keys without an attempt are blocked because their effect status cannot be proven.

## Files changed

- `appshak_substrate/schema.sql`: attempt table and index.
- `appshak_substrate/mailstore_sqlite.py`: reservation, lease/fence, outcome, publication, acknowledgment, and reconciliation transactions.
- `appshak_substrate/types.py`: source event/reply references and returned attempt ID.
- `appshak_substrate/tool_gateway.py`: durable attempt lifecycle, stored-result replay, timeout and process-tree handling.
- `appshak_substrate/agent_runtime.py`: source event binding and deferred durable result publication.
- `appshak_substrate/worker_process.py`: in-flight event heartbeat and restart finalization.
- `appshak_substrate/supervisor.py`: unique worker owner labels and process-tree termination.
- `tests/test_s1_wp2_recoverable_execution.py`: focused WP2 tests.
- This report, BATON-0004, and the current baton pointer.

## Verification

Focused WP2 tests cover active/concurrent duplicates, stored success replay, reservation recovery, uncertain effect windows, publication/ack restart windows, stale attempt and source fences, long-running renewal, nonzero failure, timeout child termination, worker crash child termination, authority continuity, worker publication, and migration. The WP1 workspace preservation tests remain in full regression.

- `python -m unittest tests.test_s1_wp2_recoverable_execution -v` — **12 passed**.
- `python -m unittest discover -s tests -p "test_*.py" -v` — **54 passed, 0 failed**.
- Chambers A, B, and C — **PASS**.
- `python -m py_compile` on changed Python files and `git diff --check` — **PASS**.

## Limits and S1-WP3 dependency

`NEEDS_RECONCILIATION` is deliberately not auto-resolved from a matching file or a worker assertion; neither proves which execution caused an effect. An operator must investigate unknown effects before any new request is authorized. Failed tool outcomes are durable and are not retried without a future explicit policy. A fail-closed Windows Job Object assignment may make a command unavailable in a host that prohibits nested jobs. No OS sandbox, approval registry, owner-task contract, or independent artifact validation was added. S1-WP3 can consume the durable attempt and outcome reference when adding its owner-task contract.

Implementation is uncommitted and unpushed for separate checkpoint review.
