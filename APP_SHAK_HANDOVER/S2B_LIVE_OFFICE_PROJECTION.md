# S2B — Live office-state projection

Status: **CERTIFIED_WITH_CORRECTIONS** after independent S2B review. The office now projects the
read-only ATS-derived S2A model. It does not write operational state or
reuse historical simulation logic. The work started from commit
`4ac38026098af161cc34a8fabb4df4b949a57ce1`.

## ATS → office mapping

`appshak-ui/src/office/projection.js` is the single deterministic boundary
between the canonical office view model and visual office meaning. It maps
the console-selected ATS task (or the same first row used by the console by
default) to state, zone, worker, task, artifact, validation, handoff,
freshness, and availability fields. Only one current worker can be projected;
other records remain console/task data and do not create live worker clones.

| ATS-derived condition | Office state | Zone |
| --- | --- | --- |
| `EXECUTING` with a running attempt | `ACTIVE / EXECUTING` | assigned worker desk |
| `VALIDATING` or running validation | `VALIDATION IN PROGRESS` | boardroom |
| persisted validation failure | `VALIDATION_FAILED` | recon desk |
| reconciliation-required outcome | `NEEDS_RECONCILIATION` | recon desk |
| validated complete with waiting dispatch | `WAITING_FOR_CAPABILITY` | dispatch zone |
| validated complete | `COMPLETE` | forge desk |
| unknown canonical meaning | `UNKNOWN` | boardroom |
| stale, unavailable, or projection error | corresponding freshness/error state | no active worker |

## Worker identity and transitions

The worker ID comes from the ATS assigned-agent field only for a current
running execution attempt. Missing assignment draws no worker. Known workers
use their desks; an unfamiliar assigned worker uses a neutral boardroom
position and retains its actual ID. Validation is represented by a work-item
marker, not by placing the execution worker in the validator role. State
changes update a static room marker. Position interpolation is permitted only
for the same worker when ATS changes its target; a different worker never
inherits a previous worker's position. Repeated identical snapshots are
idempotent.

## Stale and unavailable behavior

When the office model is stale or unavailable, the animator removes the live
worker projection, reduces the scene to a neutral state, and the scene shows
an explicit availability overlay. Any position transition is cancelled. No
task advances, completion is fabricated, or later workflow stage is entered.

## Console / office coherence

The operator console and office consume the same `useOfficeState` view model.
The office uses the console's selected task ID and first-row default.
The office projection preserves the console's raw task, validation, artifact,
handoff, and freshness semantics. `WAITING_FOR_CAPABILITY` never becomes an
external pickup, validation failure never becomes completion, and stale data
never receives current-success styling.

## Read-only guarantee

The office continues to use `GET /api/office/state`. No POST, PUT, PATCH, or
DELETE operational request was introduced. The scene and animator do not
mutate ATS, the SQLite store, task state, validation, baton, or routing data.

## Historical visual reuse and excluded simulation

No historical dashboard or stashed visual asset was imported. Existing room
geometry, styling, and renderer primitives were retained. Random agent
movement, timer-driven operational transitions, fake task generation,
mutation controls, and historical backend/state models remain excluded.

## Files changed

- `appshak-ui/src/office/projection.js` — ATS-to-office projection boundary.
- `appshak-ui/src/office/animator.js` — state-change-only worker transition animator.
- `appshak-ui/src/office/scene.js` — ATS office HUD labeling.
- `appshak-ui/src/views/OfficeView.jsx` — feeds the ATS office model to the animator.
- `appshak-ui/tests/officeState.test.mjs` — projection, idempotence, stale, and read-only tests.
- `appshak-ui/tests/s2bVisualBaseline.html` and `s2bVisualBaseline.jsx` — isolated visual fixture.
- `APP_SHAK_HANDOVER/S2B_VISUAL_BASELINES/` — six Chrome headless engineering baselines.
- `APP_SHAK_HANDOVER/S2B_LIVE_OFFICE_PROJECTION.md` — this handover report.
- `.appshak/CURRENT_BATON.json` and `BATON-0011-s2b-live-office.json` — handover projection.
- `APP_SHAK_HANDOVER/APP_SHAK_MASTER_PLAN.md` — only the S2B completion checkbox was changed.

## Independent review corrections

The original projection incorrectly treated raw `EXECUTING` as visually
working even without a running attempt and could override a failed validation.
It also prioritized historical tasks over the console's selected/default task,
placed unknown workers at the command desk, and showed no room-level marker
for non-working workflow states. The original stale screenshot was captured
before the canvas rendered.

The review corrected those issues within S2B, added focused conflict,
selection, unknown-worker, and stale-transition tests, and recaptured all six
baselines after the canvas had rendered. The master roadmap was not edited by
this review.

Timer classification: `useOfficeState` timers only poll GET and calculate
freshness; requestAnimationFrame redraws the canvas and interpolates a target
only after an ATS change. Other inspection/telemetry timers reconnect or
refresh their own read-only data. No random or timer-generated operational
task/location progression remains in the office.

## Validation

- `npm run lint`: **PASS**, zero errors.
- `npm run test:office`: **27 passed, 0 failed**.
- `npm run build`: **PASS**.
- `python -m unittest discover -s tests -p "test_*.py" -v`: **111 passed, 0 failed**.

The first full Python run reported `test_timeout_kills_child_tree` with
`RUNNING` instead of `TIMED_OUT`. The 12-test WP2 suite then passed,
including that test; a subsequent full run passed 111/111. No S1 runtime or
Python test source was changed. The cause of the first failure is unproven.

## Visual baselines

- [ACTIVE / EXECUTING](S2B_VISUAL_BASELINES/active.png)
- [VALIDATION_FAILED](S2B_VISUAL_BASELINES/validation_failed.png)
- [NEEDS_RECONCILIATION](S2B_VISUAL_BASELINES/needs_reconciliation.png)
- [COMPLETE](S2B_VISUAL_BASELINES/complete.png)
- [WAITING_FOR_CAPABILITY](S2B_VISUAL_BASELINES/waiting_for_capability.png)
- [STALE / BACKEND_UNAVAILABLE](S2B_VISUAL_BASELINES/stale_unavailable.png)

These are synthetic engineering fixtures for S2C input, not visual approval.

## Nonblocking findings

- The office projection selects one deterministic task from the bounded ATS
  snapshot; server-side pagination/filtering remains outside S2B.
- Visual baselines are synthetic and do not prove deployed production
  perceptual fidelity or live backend availability.
- The current canvas uses existing room zones; richer perceptual verification
  is deferred to S2C.
- The owner-controlled master plan has the S2B checkbox marked complete but
  its separate current-position table still says S2B is NEXT. Review
  instructions prohibited editing it.
- One transient timeout-test failure occurred in the first full Python run;
  isolated-suite and full-suite reruns passed without code changes.

Next capability: **VISUAL_VALIDATION**. Next stage: **S2C — Visual /
perceptual verification**.
