# AppShak HQ — Developer Onboarding
**Read this first. Read all of it.**

---

For the authoritative repository maturity snapshot, read
[CURRENT_STATUS.md](CURRENT_STATUS.md). For the complete documentation map,
read [docs/INDEX.md](docs/INDEX.md). This document preserves the architecture
and Phase 3B engineering boundaries under which it was written.

## What is AppShak?

AppShak is an autonomous multi-agent AI system built around a permanent North Star:

> *"This organisation exists to continuously identify valuable problems, build solutions, and increase its own capability and autonomy over time."*

It is **not** a chatbot framework. It is **not** a simple task runner. It is a governed, event-driven runtime for AI agents with persistent memory, verifiable decision flows, and measurable improvement over time.

The end product is **AGEs** — Autonomous Guided Entities — deployable as digital workers that provably outperform a fresh agent after time-in-environment.

---

## Where Are We Now?

This phase snapshot is retained as historical Phase 3B operating context. For
the reconciled repository-wide maturity and certification record, use
[CURRENT_STATUS.md](CURRENT_STATUS.md).

```
Phase 1 — Substrate          ✅ COMPLETE
Phase 2 — Reliability Layer  ✅ COMPLETE
Phase 3A — Observability     ✅ COMPLETE
Phase 3B — Certification     ❌ ACTIVE BLOCKER  ← YOU ARE HERE
Phase 4 — Controlled Autonomy
Phase 5 — External Action Layer
Phase 6 — Self-Improvement
Phase 7 — Economic Layer (AGE)
```

**Your job as a new developer is Phase 3B and nothing else.**

---

## The Hard Rules (Non-Negotiable)

These are constitutional. They are not suggestions. They govern every line of code.

1. **No phase skipping** — You cannot work on Phase 4+ until Phase 3B is certified.
2. **No autonomy before governance** — Agents do not act without the governance layer being active.
3. **No mutation before rollback** — Nothing self-modifies until rollback is implemented.
4. **No external action without Chief** — Every external call must be gated through `ChiefAgent`.
5. **No certification → no progress** — Phase 3B must produce a signed evidence bundle before anything moves.

If you are ever unsure whether something is in scope, **ask before building**.

---

## The Architecture (One Layer at a Time)

### Layer 1 — Substrate (`appshak_substrate/`)
The durable kernel. SQLite WAL event store, per-agent worker supervision, git worktree isolation.
- **Touch only if:** fixing a crash or stability bug in Phase 3B.

### Layer 2 — Projection (`appshak_projection/`)
Materialises the event stream into a semantic state view (who's doing what, office mode, stress level).
- **Touch only if:** a field is null in the certification evidence and you need to fix the projector.

### Layer 3 — Observability (`appshak_observability/`, `appshak-ui/`)
FastAPI backend + React dashboard. WebSocket stream. CCTV-style office view.
- **Touch only if:** the API is not serving or the UI won't build.

### Layer 4 — Governance (`appshak_governance/`)
Agent registry, trust/reputation scoring, boardroom arbitration, water cooler, audit ledger.
- **Read-only for Phase 3B.** Do not modify governance logic.

### Layer 5 — Integrity / Stability / Inspection (`appshak_integrity/`, `appshak_stability/`, `appshak_inspection/`)
Always-on health reporting, 6h/12h/24h stability harness, entity timeline indexing.
- **Phase 3B work lives here.** Your job is to get the 6-hour run to produce a clean evidence bundle.

---

## What Phase 3B Actually Requires

A clean 6-hour run must prove all of the following:

| Criterion | What it means |
|-----------|--------------|
| No crash, watchdog OK | Swarm runs 6h without exception killing the process |
| Event continuity | No gaps in the event log |
| Projection fully populated | No null fields in the projection view |
| Integrity + inspection fields present | Reports generate successfully |
| Decisions traceable | Governance ledger has entries |
| Replay deterministic | Replaying events produces identical state hash |
| Evidence bundle complete | All files present with valid hashes |
| Human signoff | Bladder reviews and signs the MANIFEST.json |

**Run `CERTIFICATION_HARNESS.py` — it handles all of this automatically and tells you exactly what passed and what failed.**

---

## Your Workflow

```
1. Set up your environment    →  follow ENVIRONMENT_SETUP.md
2. Run smoke tests first      →  python CERTIFICATION_HARNESS.py --quick
3. Fix any failures           →  do not proceed if chambers fail
4. Run full certification     →  python CERTIFICATION_HARNESS.py
5. Report results             →  share the MANIFEST.json output
6. Human signoff              →  Bladder reviews and signs
```

---

## What You Should NOT Do

- Do not add new features to any module
- Do not refactor working code
- Do not start Phase 4 work "in advance"
- Do not commit to `main` without a passing evidence bundle
- Do not change the governance layer
- Do not run the 6-hour test while there are uncommitted changes in the repo

---

## Repo Structure (Quick Reference)

```
AppShak_HQ/
├── appshak/                  Core library (Python API)
├── appshak_substrate/        Durable kernel + swarm supervisor
├── appshak_projection/       Event → state materializer
├── appshak_observability/    FastAPI observability backend
├── appshak-ui/               React dashboard (Vite)
├── appshak_governance/       Trust, arbitration, audit ledger
├── appshak_integrity/        Integrity reports
├── appshak_stability/        Stability harness (6h/12h/24h)
├── appshak_inspection/       Entity + office timeline indexing
├── appshak_state/            Runtime state (auto-generated, not committed)
├── tests/                    Unit tests
├── Research, docs and work/  Specifications, roadmap, references
├── Drafts/                   Constitutional documents
├── CERTIFICATION_HARNESS.py  ← START HERE for 3B
├── ENVIRONMENT_SETUP.md      ← START HERE for new machine
└── README.md                 High-level project overview
```

---

## Questions?

If something is unclear, ask before assuming. The constitution is the source of truth. When in doubt, read `Drafts/CONSTITUTIONAL INVARIANTS` and `Research, docs and work/DeveloperStack1.txt`.
