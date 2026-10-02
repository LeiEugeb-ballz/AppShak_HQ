# AppShak S1 re-entry

S1 is certified for one controlled owner-task vertical slice. The authoritative
record is [S1 Final Certification](S1_FINAL_CERTIFICATION.md); the earlier
[WP5 review](S1_WP5_SOL_HIGH_REVIEW.md) records the baton corrections. Read
those before interpreting prior phase claims.

From `E:\AppShak_HQ`, run the repeatable integrated gate:

```powershell
python -m appshak_substrate.s1_certification
```

It creates an ignored, durable fixture run under `appshak_state/s1_certification/`
and prints its SQLite database and evidence path. It exercises a real worker
request, validated artifact, baton, waiting capability handoff, restart,
duplicate prevention, failed validation, and unknown execution outcome.

The live substrate starts through `python -m appshak_substrate.run_swarm` with
the existing database and without `--reset-worktrees`. Use `--initialize-db`
only for an intentional first startup; see the exact commands in the final
certification report. The read-only `/api/office/state` endpoint exposes
canonical task, attempt, artifact, validation, baton, and routing state.

S1 does not launch a successor model, perform automatic repair, or provide a
full office UI. The verified next handoff waits for an explicitly configured
capability target.
