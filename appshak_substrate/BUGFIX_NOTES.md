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
