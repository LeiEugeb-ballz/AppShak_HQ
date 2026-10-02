# S2A-WP1 — Operator console binding to S1 truth

Status: **PASS_WITH_NONBLOCKING_FINDINGS**. The starting floor was the clean
`appshak-s1-certified` tag at `69d005dccf4023656bc95fa0218a08de72282713`.
This package changes the current `appshak-ui` console. It does not change S1
SQLite tables, task transitions, authority, validation, or baton routing.

## Canonical API contract

`GET /api/office/state` is the only S1 workflow source used by the console.
The existing observability server reads the configured mailstore in SQLite
read-only mode and returns `source: canonical_sqlite`, `tasks`, and `batons`.
Task rows contain `task_id`, `objective`, `state`, `assigned_agent`,
`workspace_id`, and arrays of attempts, artifacts, and validations. Baton rows
contain `baton_id`, `task_id`, `status`, `verification_status`,
`required_capability`, `dispatch_id`, `dispatch_status`, and `target_id`.
Missing or corrupt canonical state returns HTTP 503. The Vite `/api` proxy
routes the request to the current observability backend on port 8010. The
backend must be started with `--mailstore-db` pointing to the intended S1
mailstore; the older `/api/snapshot` is event telemetry, not task truth.

## View model and visual rule

`src/office/officeState.js` is the single mapping boundary. It preserves
canonical task/attempt/artifact/validation/baton IDs and statuses. The latest
attempt and validation are shown; the artifact is matched to the validation
by `artifact_id` when possible. Absent fields remain `null` in the model and
render as `UNKNOWN`. `selected_target` is shown only when the backend returned
a target. `WAITING_FOR_CAPABILITY` is displayed verbatim and never described
as an accepted external dispatch.

The visual `COMPLETE` badge requires task state `COMPLETE`, a persisted
`PASSED` validation, the same artifact ID, and a matching stored/validated
SHA-256. Successful execution or file existence alone cannot produce that
badge. `NEEDS_RECONCILIATION`, failed validation, and inconsistent completion
remain visibly unresolved. The raw task state is still displayed separately
so a contradictory response remains inspectable.

`src/hooks/useOfficeState.js` polls the canonical endpoint with GET every two
seconds and times out a request after five seconds. A successful read is
`LIVE / CURRENT` for at most 6.5 seconds. An older read is `STALE`.
Network/timeout failure is `BACKEND_UNAVAILABLE`; an HTTP 503 or malformed
canonical payload is `PROJECTION_ERROR`. Last-known records remain visible
with a stale warning and no current/green completion badge. No successful
read yields `UNKNOWN_STATE` until canonical data arrives. This freshness
classification is about the latest API read; it does not claim that an
unchanged durable task is itself stale.

## Components and boundary

`OfficeWorkflowPanel.jsx` shows task objectives and states, assignment,
attempt, artifact reference/digest, validation, baton verification, capability,
and routing. `OfficeView.jsx` places the panel in the existing Office view.
The canvas HUD now uses the canonical view model for its S1 status and shows
stale/error overlays. Existing room and avatar positions are illustrative;
event-driven avatar reactions are not fed into the S1 status display. The
older snapshot, inspection, and timeline views remain labeled as telemetry.
No historical dashboard code or assets were imported. No approval, task,
validation, routing, or other runtime mutation request was added. The new
operator surface uses GET only; local entity selection changes only the view.

## Validation

- `python -m unittest discover -s tests -p "test_*.py" -v`: **111 passed, 0 failed** (110 S1 baseline plus one S2A API/read-only test).
- `cd appshak-ui && npm run test:office`: **9 passed, 0 failed**, including rendered COMPLETE gating, failed/unknown states, waiting, stale/error, ID mapping, and GET-only UI path.
- `cd appshak-ui && npm run build`: **PASS**.
- Scoped ESLint on changed UI source and tests: **PASS**.
- Repository-wide `npm run lint`: two existing `react-hooks/set-state-in-effect` errors in unchanged `src/hooks/useInspectionData.js` at lines 143 and 148. No S2A file has a lint error.
- Full Office View browser DOM against the existing S1 certification mailstore: **PASS**. The live `GET /api/office/state` response and rendered console show `NEEDS_RECONCILIATION`, `VALIDATION_FAILED`, and a validated `COMPLETE` task with `BATON-0008` verified but `WAITING_FOR_CAPABILITY` and no selected target. This is a controlled fixture, not an operational deployment claim.

The E: volume lacked room for `npm ci`; locked dependencies were installed
under C: and linked into the ignored UI `node_modules` path. No dependency
manifest or lockfile was rewritten. `dist` and `node_modules` remain ignored.
Vite resolves React and React DOM as singletons so the linked local dependency
directory does not create a duplicate-React blank screen in the dev server.

## Visual baseline

Six screenshots were captured with the existing Chrome headless browser from
`appshak-ui/tests/visualBaseline.html`. That page renders the production
`OfficeWorkflowPanel` and view-model code with isolated synthetic fixtures;
production `App.jsx` never imports the fixture. These are component baselines,
not live-backend proof or visual approval:

- [Active task](S2A_VISUAL_BASELINES/active.png)
- [Validating](S2A_VISUAL_BASELINES/validating.png)
- [Completed](S2A_VISUAL_BASELINES/completed.png)
- [Failed validation](S2A_VISUAL_BASELINES/failed.png)
- [Waiting for capability](S2A_VISUAL_BASELINES/waiting.png)
- [Stale and backend unavailable](S2A_VISUAL_BASELINES/stale_error.png)

The next bounded work is **S2A-WP2 — Operator usability and workflow
inspection**. It can evaluate the console with a running S1 mailstore and
its read-only backend; no external baton pickup or operator mutation is
claimed in WP1.
