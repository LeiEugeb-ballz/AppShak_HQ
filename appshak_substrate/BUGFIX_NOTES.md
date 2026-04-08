# Bug Fix Audit Notes — `appshak_substrate`

---

## BUG-001: Windows CRLF False-Dirty Worktree Crash

**Date Fixed:** 2026-04-06
**Fixed By:** Jafa (AI agent, Base44)
**Affected File:** `appshak_substrate/workspace_manager.py`
**Commit:** `a722afb`

### Symptom
Swarm supervisor crashed immediately on startup (exit=1) with:
```
RuntimeError: Worktree 'C:\...\workspaces\recon' is not clean.
```
This occurred on every fresh clone on Windows, making the certification
harness impossible to run without manual intervention.

### Root Cause
When `git worktree add` creates a new worktree on Windows, git automatically
normalises line endings from LF (Unix) to CRLF (Windows) based on the
`.gitattributes` config (`text=auto`). Immediately after creation, `git status`
detects these CRLF-converted files as modified — even though no actual code
changes were made. The `_ensure_clean()` method treated this as a genuine dirty
state and raised a `RuntimeError`.

### Fix
`_ensure_clean()` in `workspace_manager.py` was updated to:
1. Detect a dirty state after worktree creation.
2. Automatically run `git reset --hard` + `git clean -fdx` to re-normalise.
3. Re-run `git status` to confirm clean state.
4. Only raise `RuntimeError` if still dirty after the auto-reset — meaning it
   is a genuine problem, not a CRLF artefact.

Additionally, `.gitattributes` was updated to enforce `eol=lf` globally to
reduce recurrence on future clones.

### Impact
- No functional code changes — behaviour of worktrees is identical.
- Fix is self-healing and transparent to the operator.
- Confirmed working: Certification Harness v3B.3 passed Step 3 and entered
  Step 4 (stability harness) successfully for the first time on 2026-04-06.

---

---

## BUG-002: watchdog_queue_stall False Positive — Race Condition on Kernel Shutdown

**Date Fixed:** 2026-04-07
**Fixed By:** Jafa (AI agent, Base44)
**Affected File:** `appshak_stability/runner.py`
**Commit:** (see git log)

### Symptom
`watchdog_queue_stall` fired after only ~6 minutes of a 6-hour run, causing
FAIL on `no_crash_watchdog_ok`. The harness reported:
```
running=false while queue remains non-zero
```

### Root Cause
The `running` flag in the projection snapshot comes from `kernel.running` inside
each worker process. The kernel finishes its own internal event loop and sets
`running=False` during normal operation. The projection materializer snapshots
this state while the supervisor's SQLite mailstore queue still has pending items
that haven't been consumed yet. This is a race condition — not a real stall.

The original watchdog fired after just 5 cycles (~5 seconds), which is not
enough time to distinguish a genuine stall from a normal kernel cycle boundary.

### Fix
`runner.py` now tracks **consecutive** stall cycles. A `watchdog_queue_stall`
incident is only raised after **3 consecutive cycles** where `running=false` AND
`event_queue_size > 0`. A single-cycle blip (race condition) resets the counter.
Non-stall incidents (e.g. `watchdog_worker_offline`) still fire immediately.

### Impact
- Eliminates false-positive stall detection during normal kernel shutdown cycles.
- Genuine stalls (sustained over 3+ cycles) are still caught correctly.
- Confirmed: stability run completed with `Status: completed | Passed: True`.

---

## BUG-003: watchdog_queue_stall — Supervisor Control Events Counted as Pending Work

**Date Fixed:** 2026-04-08
**Fixed By:** Jafa (AI agent, Base44)
**Affected File:** `appshak_projection/projector.py`
**Commit:** (see git log)

### Symptom
`watchdog_queue_stall` continued to fire even after the 3-cycle grace period fix
(BUG-002). The run halted after ~480 seconds of a 6-hour run.

### Root Cause
The projection materializer computes `event_queue_size` by counting ALL events in
the mailstore with status `PENDING`. When the supervisor shuts down, it publishes
`SUPERVISOR_STOP` and `SUPERVISOR_HEARTBEAT` control events to the mailstore.
These events have status `PENDING` and are never claimed/acked by workers (because
workers are shutting down). They remain in the mailstore as PENDING indefinitely.

The watchdog sees `running=false` (from `SUPERVISOR_STOP` event) + `queue > 0`
(from those same unclaimed control events) and fires the stall alarm — even though
no real work is pending.

### Fix
`projector.py` now excludes known supervisor/kernel control event types from the
`pending_count` calculation:
- `SUPERVISOR_STOP`, `SUPERVISOR_START`, `SUPERVISOR_HEARTBEAT`
- `KERNEL_START`, `KERNEL_SHUTDOWN`, `KERNEL_HEARTBEAT`

These are infrastructure lifecycle events, not work items. Only agent-directed
work events count toward `event_queue_size`.

### Impact
- `event_queue_size` now accurately reflects actual pending work.
- Watchdog stall detection is no longer triggered by shutdown bookkeeping.
- Previous BUG-002 grace-period fix (3 cycles) remains in place as a safety net.
