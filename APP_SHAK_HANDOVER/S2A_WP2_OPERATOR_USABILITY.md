# S2A-WP2 — Operator usability and workflow inspection

Status: **PASS_WITH_NONBLOCKING_FINDINGS**. The package starts from clean,
synchronized commit `72062838189f02b3e32582644509b8f4936797e1`. It extends
the read-only S2A-WP1 console; it does not alter S1 task transitions,
validation gates, capability routing, or runtime authority.

## Usability inspection

The WP1 console exposed canonical fields but presented every task as a large,
flat record. Raw IDs, paths, and hashes dominated the view. Current and prior
attempts were not distinguished, validation evidence and failure reasons were
not projected, task-to-artifact-to-validation lineage was implicit, and baton
verification was visually adjacent to routing without explaining the waiting
boundary. Canonical workflow state appeared below telemetry, which made the
authority distinction harder to scan. There was no task selection or concise
multi-task overview.

## Workflow inspection model

The current console presents each task as the following read-only chain:

`OBJECTIVE → ASSIGNMENT → EXECUTION → ARTIFACT → VALIDATION → COMPLETION → BATON → ROUTING / HANDOFF`

`appshak_projection/office_state.py` still opens SQLite in read-only mode. Its
existing `GET /api/office/state` response now includes canonical timestamps,
owner and assignment authority/source, all ordered attempts and their stored
outcomes, artifacts, acceptance criteria, validation evidence/checks, baton
lineage and verification reason, and dispatch reason/timestamps. JSON columns
are decoded for inspection; invalid JSON is exposed as unknown rather than
invented content. No route or table mutation was added.

`appshak-ui/src/office/officeState.js` remains the single UI mapping boundary.
It maps the full chronology and marks the last canonical attempt/validation as
current. Earlier records remain explicitly labelled previous. Presentation
grouping is derived from canonical states and never replaces the raw task
state. Overview counts may overlap, for example a validated COMPLETE task can
also be WAITING_FOR_CAPABILITY.

## Task overview and detail

The overview shows directly derived counts, objective, presentation grouping,
and raw canonical state. Keyboard-focusable task buttons change only local
React selection in `OfficeView`; the panel has no network client. The selected
task exposes canonical IDs, owner/authority references, worker and workspace,
attempt chronology, every artifact and digest, validation lineage/evidence,
completion gate facts, baton lineage, required capability, routing reason,
and an actual target only when canonical state supplies one. Long values wrap
and retain their full value in text/title attributes.

## Failure, uncertainty, and validation

The console uses distinct labels and explanations for execution failure,
unknown/reconciliation outcomes, validation failure, and validation process
error. Missing reasons render `UNKNOWN`. Backend unavailable and projection
error remain separate from durable workflow failures. Stale last-known data
loses current success styling and is accompanied by an explicit warning.

Validation inspection identifies the artifact, validator, related attempt,
validated digest, completion time, stored reason, and every projected check's
type, required flag, expected configuration, observed evidence, and result.
The existing WP1 completion condition remains unchanged: COMPLETE requires a
persisted PASS linked to the displayed artifact with matching stored and
validated SHA-256 values.

## Baton and handoff

The task detail exposes baton/source IDs, verification status and reason,
validation/Git lineage, required capability, next objective, dispatch ID and
status, routing reason, target, and timestamps where present.
WAITING_FOR_CAPABILITY is explained as verified work ready for a capability
with no eligible external target configured; it explicitly does not claim
pickup or dispatch.

## Canonical truth and telemetry

The authoritative workflow console now appears before the office telemetry.
The existing scene, entity inspection, event timelines, integrity, and
stability data remain available under a visible
`Telemetry / Events / Observability` heading labelled non-authoritative.
No event or animation is allowed to update canonical task meaning.

## Read-only network guarantee

The canonical workflow hook continues to issue only `GET
/api/office/state`. Task selection and disclosure controls are local browser
interactions. Tests inspect the workflow source for POST, PUT, PATCH, DELETE,
fetch, XMLHttpRequest, WebSocket, and operational action paths. The backend
route remains GET-only, and a byte-for-byte database comparison around the
certification API read confirms the inspected SQLite file is unchanged.

## Files changed

- `appshak_projection/office_state.py` — extended read-only canonical fields.
- `appshak-ui/src/office/officeState.js` — chronology, linkage, grouping, and failure mapping.
- `appshak-ui/src/components/OfficeWorkflowPanel.jsx` — task overview and workflow inspection.
- `appshak-ui/src/views/OfficeView.jsx` — local selection and canonical/telemetry hierarchy.
- `appshak-ui/src/App.css` — bounded responsive/readable inspection styles.
- `appshak-ui/tests/officeState.test.mjs` — 16 focused operator/read-only tests.
- `appshak-ui/tests/wp2VisualBaseline.html` and `wp2VisualBaseline.jsx` — isolated baseline fixture.
- `tests/test_s2a_wp1_operator_console.py` — expanded projection and database read-only evidence.
- `docs/INDEX.md` — report navigation.
- `.appshak/CURRENT_BATON.json` and `BATON-0010-s2a-wp2.json` — repository handover projection.

No dependency manifest, lockfile, historical dashboard, or runtime mutation
module changed.

## Validation

- `npm run lint`: **PASS**, zero errors.
- `npm run test:office`: **16 passed, 0 failed**.
- `npm run build`: **PASS**.
- `python -m unittest discover -s tests -p "test_*.py" -v`: **111 passed, 0 failed**.
- `git diff --check`: **PASS**.

## Visual baselines

Seven Chrome headless engineering baselines render the production component
and mapping code with isolated synthetic records. They are not S2C visual
approval or evidence of a deployed live office:

- [Multi-task overview](S2A_VISUAL_BASELINES/WP2/overview.png)
- [Active task](S2A_VISUAL_BASELINES/WP2/active.png)
- [Validation failure](S2A_VISUAL_BASELINES/WP2/validation_failure.png)
- [Needs reconciliation](S2A_VISUAL_BASELINES/WP2/needs_reconciliation.png)
- [Completed task](S2A_VISUAL_BASELINES/WP2/completed.png)
- [Waiting for capability](S2A_VISUAL_BASELINES/WP2/waiting_for_capability.png)
- [Stale/backend unavailable](S2A_VISUAL_BASELINES/WP2/stale_unavailable.png)

## Remaining S2A limitations

The endpoint returns a bounded snapshot (default 100 records) and the task
overview has no server-side pagination or filtering. Visual baselines are
synthetic component fixtures. S2A does not claim live office movement,
external capability dispatch, operational controls, or perceptual approval.
`APP_SHAK_HANDOVER/S2_MASTER_PLAN.md` is absent, so no roadmap checkbox was
marked.

The expected next major stage, if this package is accepted, is **S2B — Live
office-state projection**. This package does not begin S2B.
