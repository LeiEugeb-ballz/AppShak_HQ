# S1 final integration and restart certification

Status: **PASS_WITH_NONBLOCKING_FINDINGS** for the controlled S1 vertical
slice. Starting repository commit: `406fdef0500b5fa2a7c32b53042c67df14db9deb`.
At entry, `main`, `origin/main`, and the remote `main` matched; the working
tree was clean. BATON-0007 was current and recorded independent Sol High review.
The incoming full regression was 107 passing tests.

## What is certified

The existing substrate now supports a bounded path from an owner-created
durable task through assignment, Chief-authorized worker execution, a durable
attempt, a file artifact, independent deterministic validation, gated task
completion, a verified SQLite baton, and a durable capability handoff. The
handoff is `WAITING_FOR_CAPABILITY` when no target is explicitly configured.
This is a real file and SQLite workflow in a controlled Git fixture, not a
claim of autonomous production operation.

The integrated command below creates a fresh ignored run directory, real Git
repository and worker worktree, and a SQLite mailstore. Its result JSON gives
the exact paths and IDs. Reopening the same SQLite file recovers the same task,
assignment, authority, attempt, artifact digest, validation, baton, route,
dispatch ID, and context pack. A repeated worker request preserves the output
file modification time and attempt count; repeated baton evaluation preserves
the dispatch ID. A wrong artifact fails validation and cannot verify a success
baton. An expired execution lease becomes `NEEDS_RECONCILIATION`; a stale
worker cannot persist success, and no success baton can dispatch from it.

```powershell
python -m appshak_substrate.s1_certification
```

The certification runner's canonical SQLite file is
`appshak_state/s1_certification/run-<id>/mailstore.db`; its real fixture
repository and worker worktree are beside it. The latest accepted run is
recorded in [BATON-0008](../.appshak/batons/BATON-0008-s1-certification.json).
The repository checkpoint chain BATON-0007 → BATON-0008 is a handover record.
The fixture's SQLite BATON-0008 is its own verified root because pre-WP5
repository handovers did not have canonical owner-task/validation records.
The filesystem handover is not imported as a trusted runtime predecessor.

## Live startup and observation

The live substrate's canonical database is
`E:\AppShak_HQ\appshak_state\substrate\mailstore.db`. Its one startup entrypoint
is `appshak_substrate.run_swarm`. A missing database is rejected by default.
For the first intentional startup only, add `--initialize-db` to this command:

```powershell
python -m appshak_substrate.run_swarm --agents recon forge command --durable --worktrees --repo-root E:\AppShak_HQ --db-path E:\AppShak_HQ\appshak_state\substrate\mailstore.db --duration-seconds 1200
```

No startup command uses `--reset-worktrees`. Starting the swarm does not by
itself create an owner objective or start autonomous model work. The owner-task
API/CLI is an explicit intake boundary. To inspect live canonical office
state, start the existing observability server with the same database:

```powershell
python -m appshak_observability.server --mailstore-db E:\AppShak_HQ\appshak_state\substrate\mailstore.db --host 127.0.0.1 --port 8010
```

`GET http://127.0.0.1:8010/api/office/state` reads SQLite in read-only mode.
It exposes task ID/objective/state, assignment worker/workspace/authority,
attempt ID/state, artifact ID/reference/stored SHA-256 and size, validation
status, baton ID/verification state, required capability, and selected target
or waiting status. Missing or corrupt canonical state returns HTTP 503; it is
never replaced with a fabricated empty office. The existing snapshot/UI path
remains separate and is not certified as a complete task visualization.

## State and architecture

The bounded task states are `CREATED` → `ASSIGNED` → `EXECUTING` →
`READY_FOR_VALIDATION` → `VALIDATING` → `COMPLETE`, with distinct execution,
validation, and reconciliation failure states. An artifact is recorded after
a successful worker write; only a persisted independent PASS advances to
COMPLETE. SQLite mail, lease, attempt, task, artifact, validation, baton,
history, and dispatch tables are the durable authority. Workspace files and
the ignored run evidence remain on disk. `CURRENT_BATON.json` and baton JSON
are handover projections, not runtime authority.

WP5 baton states include `DRAFT`, `VERIFYING`, `VERIFIED`, `REJECTED`, and
`SUPERSEDED`. Verification checks task and validation truth, repository/Git
basis, evidence confinement, and lineage. Capability policy is separate from
provider/model configuration. Only a verified baton can create one durable
dispatch record. Without a configured target it remains waiting; no external
model execution is claimed.

## Certification evidence

- Integrated S1 workflow: PASS, nine named checks.
- Focused WP6 tests: 3 passed, 0 failed.
- Full unittest discovery: 110 passed, 0 failed.
- Chambers A, B, C: PASS.
- Source compilation, JSON parsing, and `git diff --check`: PASS.

An earlier run of the full suite alongside the chambers and certification
runner reported one failure and one error; that invocation did not retain the
test names. The subsequent standalone full suite passed 110/110. This remains
an uncharacterized concurrent-run observation, not a certified concurrency
property of the test harness.

## Classification

| Area | Classification | Basis |
|---|---|---|
| Repository | CERTIFIED | Clean synchronized starting commit and scoped WP6 worktree. |
| Workspace safety | CERTIFIED | Existing worktree content survives repeated setup and restart. |
| Execution authority | CERTIFIED | Assigned command worker and authority persist; gateway policy is enforced. |
| Recoverable attempts | CERTIFIED | Durable reservation, stale fence, unknown outcome, duplicate prevention. |
| Durable owner tasks | CERTIFIED | Task identity and state reopen from SQLite. |
| Assignment | CERTIFIED | Agent, workspace, and authority reopen unchanged. |
| Artifacts | CERTIFIED | Real output reference, size, and SHA-256 persist. |
| Validation | CERTIFIED | Independent read and persisted PASS/FAIL. |
| Completion gate | CERTIFIED | Only PASS completes; failed/unknown paths do not. |
| Baton verification | CERTIFIED | Runtime baton checks canonical task, validation, Git, and evidence. |
| Capability routing | CERTIFIED | Deterministic policy and fail-closed unconfigured route. |
| Dispatch boundary | PARTIAL | Durable waiting handoff; no external provider execution interface. |
| Restart recovery | CERTIFIED | Same IDs, records, route, and context reopen. |
| Office-state projection | CERTIFIED | Read-only API derives directly from canonical SQLite. |

## Limits and next direction

S1 certifies one bounded UTF-8 file artifact path. It does not certify a
general artifact registry, automatic repair, provider execution, long-horizon
planning, desktop model switching, or full UI task visualization. The
certification fixture is isolated from the live mailstore; its pass does not
assert that a live deployment has run the same owner objective. The ignored
run directory preserves evidence locally and is not part of the Git commit.

The next engineering direction is an explicit post-S1 architecture review of
the durable handoff and operator-facing workflow, followed by separately
authorized integration work. No commercial successor model is selected here.

Read [00_READ_ME_FIRST.md](00_READ_ME_FIRST.md) for the short re-entry route,
then the [WP5 review](S1_WP5_SOL_HIGH_REVIEW.md) for baton trust boundaries.
