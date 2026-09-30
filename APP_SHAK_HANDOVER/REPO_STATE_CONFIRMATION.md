# AppShak Repository State Confirmation

## 1. Canonical repository decision

`E:\AppShak_HQ` is the canonical repository selected for continuation.

Evidence:

- It is the only candidate with a Git repository, current branch, remote, and complete active source/documentation tree.
- `main` is at `6ecf84b99bee3ddb0ccd76c0358e569e8a848167` (`Document archived dashboard preview status`).
- `origin/main` and `origin/HEAD` point to the same synchronized history.
- RC1-A artifacts are present: `README.md`, `docs/INDEX.md`, `CURRENT_STATUS.md`, and `docs/DEPENDENCIES.md`.
- The existing unittest suite completed successfully: 37 tests, `OK`.

## 2. Candidate comparison

| Candidate | Evidence | Classification |
|---|---|---|
| `C:\AppShak_HQ` | Does not exist at confirmation time. | INCOMPLETE COPY / ABSENT |
| `E:\AppShak_HQ` | Git repository on `main`; HEAD `6ecf84b`; remote configured; clean before baton; active source, UI, tests, state implementation, documentation, and certification evidence present. | ACTIVE WORKING REPOSITORY |
| `E:\AppShak_HQ-main` | Directory exists but is not itself a Git repository; contains a nested `AppShak_HQ-main` directory that is also not a Git repository. The nested snapshot lacks `docs/INDEX.md`, `CURRENT_STATUS.md`, and `docs/DEPENDENCIES.md`. | SNAPSHOT / STALE CLONE |

The `E:\AppShak_HQ-main` nested tree contains older source and evidence material, but no Git metadata, branch, remote, or verifiable checkpoint identity.

## 3. Git state

- Canonical root: `E:\AppShak_HQ`
- Branch: `main`
- HEAD: `6ecf84b99bee3ddb0ccd76c0358e569e8a848167`
- HEAD date: `2026-08-22T18:57:47+02:00`
- HEAD subject: `Document archived dashboard preview status`
- Working tree before baton: clean; `git status --porcelain` produced no entries.
- Remote: `origin` configured to the AppShak GitHub repository.
- Remote sync: `HEAD...origin/main = 0 0`; `origin/HEAD -> origin/main`.
- Relevant history includes `71ad526` (RC1-A documentation curation checkpoint), `cd8a3dc` (`rc1-a-checkpoint`), and Phase 2–4 certification commits/tags.

The baton files and this report are the only intended writes from this confirmation task. They are intentionally distinguished from the pre-write clean state.

## 4. Repository structure

Active implementation areas present at the root include:

- `appshak/`: core kernel, agents, memory, event bus, safeguards, and plugins.
- `appshak_substrate/`: durable SQLite mailstore, worker runtime, supervisor, worktree manager, and enforcement chambers.
- `appshak_projection/`: event-to-view projection and materializer.
- `appshak_observability/`: FastAPI/WebSocket observability backend.
- `appshak-ui/`: React/Vite frontend.
- `appshak_governance/`: registry, arbitration, relationship, replay, and audit ledger.
- `appshak_integrity/`, `appshak_stability/`, `appshak_inspection/`: validation and operational evidence layers.
- `tests/`: 37 discovered unittest cases.
- `docs/`, `Research, docs and work/`, `Drafts/`, and `run_archives/`: active documentation, research, constitutional material, and preserved evidence/history.

## 5. Entry points and startup

- Core runtime: `python -m appshak` (`appshak/__main__.py`).
- Durable kernel runtime: `python -m appshak_substrate.run_kernel_durable`.
- Durable swarm supervisor: `python -m appshak_substrate.run_swarm --agents recon forge command --durable --worktrees --duration-seconds 1200`.
- Observability backend: `python -m appshak_observability.server --host 127.0.0.1 --port 8010 --projection-view appshak_state/projection/view.json`.
- Projection materializer: `python -m appshak_projection.run_projector --mailstore-db appshak_state/substrate/mailstore.db --view-path appshak_state/projection/view.json --poll-interval 1`.
- UI: `cd appshak-ui; npm install; npm run dev`.

## 6. Dependencies and build

- No root `pyproject.toml`, `setup.py`, `setup.cfg`, or active root `requirements.txt` is tracked.
- Canonical dependency guidance is `docs/DEPENDENCIES.md`.
- UI manifests are `appshak-ui/package.json` and `appshak-ui/package-lock.json`.
- Test configuration is `pytest.ini`; the available environment does not have the `pytest` module installed.
- Documented test command: `python -m unittest discover -s tests -p "test_*.py" -v`.
- Observed test result during confirmation: 37 tests ran and passed.
- UI build command: `cd appshak-ui; npm run build`. It was identified but not executed during this confirmation.
- No `.github` workflow, Dockerfile, or docker-compose file was found by the repository file scan.

## 7. Persistent state

- Durable event state: SQLite mailstore at `appshak_state/substrate/mailstore.db`, implemented by `appshak_substrate/mailstore_sqlite.py`.
- Global memory: JSON state rooted at `appshak_state`, implemented by `appshak/memory.py`.
- Projection state: JSON view at `appshak_state/projection/view.json`, implemented by `appshak_projection/view_store.py`.
- Governance state: registry and audit-ledger paths are configurable through `appshak_governance` components.
- `appshak_state/` is ignored runtime output; preserved historical runtime evidence exists under `run_archives/` and `untraacked_20260503/`.
- `STATE_PERSISTENCE_IMPLEMENTED`: YES.

## 8. Architecture match

**MOSTLY_MATCH**

The active tree materially contains the documented substrate, projection, observability, governance, integrity/stability/inspection, agent, orchestration, tool-gateway, memory, and audit components. Existing documentation records incomplete Phase 4 operational evidence and retains older Phase 3B operating-context language. Those are status/evidence distinctions, not an absence of the corresponding implementation layers.

## 9. Repository hygiene findings

Observed facts only:

- No nested Git repositories were found under the canonical root.
- No tracked `.env`, PEM, key, credential, token-named, database, `node_modules`, `dist`, `build`, or Python-cache paths were found by the tracked-path scan.
- The repository intentionally tracks preserved PDFs, screenshots, HTML exports, ZIP archives, an MP3, DOCX research, JSON/JSONL evidence, and generated historical run artifacts.
- Large preserved evidence includes JSON/JSONL runtime snapshots and research documents; these are under archival/research/run-history paths.
- A sensitive-name heuristic matched labels in an archived static HTML file; no credential value was emitted or assessed from that match.
- `run.log` is present at the root.

## 10. Blocking and non-blocking findings

### Blocking findings

None for repository identity or continuation.

### Non-blocking findings

- No root Python dependency manifest is tracked; dependency guidance is documentation-only.
- `pytest` is unavailable in the current Python environment, while the repository's unittest suite is runnable and passed.
- Historical onboarding text retains Phase 3B operating-context language while `CURRENT_STATUS.md` is the reconciled repository-wide status snapshot.
- Preserved historical/generated artifacts, archives, reports, binary references, and run evidence remain in the repository by design.
- UI build was not executed during this confirmation.

## 11. Readiness decision

**READY_WITH_NONBLOCKING_FINDINGS**

The canonical repository is identifiable, synchronized, structurally coherent, documented, and testable. The findings above do not prevent a subsequent engineering model from beginning the next authorized capability, but they remain part of the handover record.

## 12. Recommended next capability

`ARCHITECTURAL_AUDIT`

## 13. Baton

- JSON baton: `E:\AppShak_HQ\.appshak\batons\BATON-0001-repo-state.json`
- Current baton pointer: `.appshak/CURRENT_BATON.json`

This confirmation stops at repository state confirmation. No corrective implementation, architecture redesign, cleanup, commit, push, reset, rebase, or source modification was performed.
