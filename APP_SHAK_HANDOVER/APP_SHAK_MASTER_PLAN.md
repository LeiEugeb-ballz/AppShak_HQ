\# AppShak Master Plan



Owner-controlled roadmap and progress tracker.



This file is the fixed high-level project direction agreed between the Owner

and ChatGPT co-engineer.



It exists to prevent roadmap drift between implementation sessions, models,

agents, audits, and future resumptions.



It is NOT implementation documentation.

It is NOT generated architecture.

It is NOT a place for coding agents to redefine AppShak.



\---



\# CONTROL RULE



Codex and other implementation agents may READ this file.



They may modify this file ONLY by changing an existing completed checklist item:



\[ ]



to:



\[x]



after that exact stage or work package has passed its acceptance gate.



Implementation agents MUST NOT:



\- add roadmap items

\- remove roadmap items

\- rename roadmap items

\- reorder roadmap items

\- rewrite descriptions

\- add notes

\- add sub-stages

\- redefine scope

\- reinterpret future stages

\- change constitutional principles

\- mark future work complete without its defined acceptance gate



Any roadmap change other than an existing `\[ ]` → `\[x]` completion mark requires

Owner + ChatGPT co-engineer agreement outside the implementation loop.



Implementation prompts may temporarily subdivide a stage into bounded work

packages, but those subdivisions do not alter this master roadmap unless the

Owner explicitly adds them here.



\---



\# PERMANENT CONSTITUTIONAL UI RULE



The AppShak UI is permanently READ-ONLY with respect to the kernel/runtime.



The UI may:



\- receive canonical backend state

\- interpret it

\- organize it

\- filter/sort/select it locally

\- visualize it

\- animate representations of it

\- expose history, evidence, artifacts, validation and routing state



The UI must NEVER:



\- mutate kernel/runtime state

\- alter tasks

\- alter worker state

\- approve or deny execution

\- trigger retries

\- trigger validation

\- change routing

\- select execution models

\- dispatch work

\- affect operational state



Required direction:



CANONICAL BACKEND TRUTH

&#x20;       ↓

READ-ONLY PROJECTION

&#x20;       ↓

UI INTERPRETATION

&#x20;       ↓

HUMAN OBSERVATION



Never the reverse.



\---



\# S1 — DURABLE TRUTH



Goal:

Turn AppShak from an uncertain collection of architecture/components into a

persistent, auditable, recoverable work engine.



\## S1 Foundation / Recovery



\[x] Repository state confirmation



Canonical repository confirmed:



E:\\AppShak\_HQ



Historical/stale repository candidates rejected.



Repository readiness established before corrective implementation.



\[x] Independent architectural audit



Existing durable queues, supervised processes, execution, observability and

persistence were confirmed reusable.



Critical missing vertical-slice contracts were identified and converted into

bounded work packages.



\## S1 Runtime Stabilization



\[x] S1-WP1 — Preserve workspaces and bind execution authority



Established:



\- non-destructive durable workspace reuse

\- explicit execution authority

\- worker/workspace/operation attribution

\- fail-closed invalid authority handling



\[x] S1-WP2 — Make execution attempts recoverable



Established:



\- durable execution attempt lifecycle

\- idempotency

\- lease renewal

\- execution fencing

\- crash reconciliation

\- long-running execution support

\- timeout / child-process handling

\- safe UNKNOWN outcome behavior



\[x] S1-WP3 — Add durable owner-task contract



Established:



\- durable owner task identity

\- durable assignment

\- task ↔ execution attempt linkage

\- persistent task history

\- distinct FAILED vs UNKNOWN states

\- no implicit retry



\[x] S1-WP4 — Gate artifacts with persisted validation



Established:



\- durable artifact references

\- acceptance criteria

\- independent validation

\- integrity binding

\- persisted PASS / FAIL / ERROR

\- validation-gated task completion



\[x] S1-WP5 — Connect capability routing and verified batons



Established:



\- durable canonical baton state

\- verified baton lineage

\- fail-closed baton verification

\- capability-based routing

\- provider/model separation

\- deterministic routing policy

\- idempotent dispatch state

\- WAITING\_FOR\_CAPABILITY boundary

\- no fabricated external execution



\[x] S1-WP6 — Project verified slice and certify restart



Certified integrated flow:



OWNER

&#x20; ↓

DURABLE TASK

&#x20; ↓

ASSIGNMENT

&#x20; ↓

AUTHORIZED EXECUTION

&#x20; ↓

RECOVERABLE ATTEMPT

&#x20; ↓

DURABLE ARTIFACT

&#x20; ↓

INDEPENDENT VALIDATION

&#x20; ↓

VALIDATED COMPLETION

&#x20; ↓

VERIFIED BATON

&#x20; ↓

CAPABILITY ROUTING

&#x20; ↓

DURABLE HANDOFF / WAITING



\[x] S1 certification checkpoint



Certified baseline:



Commit:

69d005dccf4023656bc95fa0218a08de72282713



Tag:

appshak-s1-certified



Certification result:



110 tests passed

Chambers A/B/C passed

Integrated S1 certification passed

main synchronized with origin

clean working tree



S1 is the protected architectural floor.



Future work must not weaken S1 contracts.



\---



\# S2 — HUMAN-OBSERVABLE OFFICE



Goal:

Make the certified AppShak engine understandable, observable and believable to

a human without allowing the UI to influence operations.



\---



\# S2A — OPERATOR INTERACTION / INSPECTION



Goal:

Allow a human operator to understand canonical AppShak work state without

opening SQLite, source code or raw logs.



\[x] S2A-WP1 — Bind operator console to certified S1 truth



Established:



\- existing React/Vite appshak-ui retained

\- `/api/office/state` used as canonical S1 workflow source

\- task/execution/artifact/validation/baton/routing truth exposed

\- truthful COMPLETE gating

\- stale/error/unknown states represented

\- read-only UI boundary preserved

\- no historical simulation logic revived



\[x] S2A maintenance — Clean pre-existing UI lint errors



Established clean engineering floor:



\- repository-wide lint: 0 errors

\- UI build: PASS

\- Python regression: PASS

\- no intended behavioral change



\[x] S2A-WP2 — Operator usability / workflow inspection



Established operator-readable flow:



TASK

&#x20; ↓

ASSIGNMENT

&#x20; ↓

EXECUTION

&#x20; ↓

ARTIFACT

&#x20; ↓

VALIDATION

&#x20; ↓

COMPLETION

&#x20; ↓

BATON

&#x20; ↓

HANDOFF



Operator can distinguish:



\- current state

\- history

\- execution failure

\- validation failure

\- unknown/reconciliation state

\- stale state

\- backend/projection failure

\- WAITING\_FOR\_CAPABILITY

\- canonical state vs telemetry



UI remains permanently read-only.



\---



\# S2B — LIVE OFFICE-STATE PROJECTION



Goal:

Make the office itself a truthful visual projection of canonical AppShak state.



\[x] S2B — Live office-state projection



Required direction:



CANONICAL STATE

&#x20;     ↓

OFFICE STATE MAPPING

&#x20;     ↓

ROOM / AGENT VISUAL STATE

&#x20;     ↓

ANIMATION



The office must never infer backend truth from animation.



Expected scope includes:



\- map canonical workflow state to office concepts

\- bind workers/agents to truthful visual locations

\- represent working / waiting / validating / failed / complete states

\- represent artifact transfer where meaningful

\- represent capability waiting honestly

\- preserve stale/error visibility

\- keep existing historic visual shells as reference/assets only

\- prohibit simulation/random activity from becoming operational truth



Historical office/CCTV/3D work may be reused for:



\- layout

\- scene composition

\- avatars

\- styling

\- transitions

\- animation ideas



Historical state logic must not return.



\---



\# S2C — VISUAL / PERCEPTUAL VERIFICATION



Goal:

Close the gap between code-correct visuals and what a human actually sees.



\[ ] S2C — Visual / perceptual verification



Required verification layers:



1\. SEMANTIC TRUTH



Does rendered UI match canonical backend state?



This should be deterministic wherever possible.



2\. STRUCTURAL VISUAL CORRECTNESS



Examples:



\- clipping

\- overlaps

\- missing elements

\- wrong state representation

\- unreadable labels

\- broken layout

\- incorrect orientation

\- discontinuous animation



3\. PERCEPTUAL QUALITY



Compare rendered screenshots/video against known-good visual references.



Use strong multimodal review where useful.



Visual reviewer produces bounded findings.



It must not autonomously redesign AppShak.



Required loop:



RENDER

&#x20; ↓

VISUAL REVIEW

&#x20; ↓

BOUNDED FINDINGS

&#x20; ↓

BOUNDED FIX

&#x20; ↓

RENDER AGAIN



Final aesthetic/perceptual acceptance remains a human gate.



\---



\# S2D — EXTERNAL CAPABILITY HANDOFF



Goal:

Turn S1's honest `WAITING\_FOR\_CAPABILITY` boundary into real external work

pickup without weakening baton verification.



\[ ] S2D — External capability handoff



Target flow:



VERIFIED BATON

&#x20;     ↓

REQUIRED CAPABILITY

&#x20;     ↓

ROUTING POLICY

&#x20;     ↓

AVAILABLE EXTERNAL TARGET

&#x20;     ↓

CONTEXT PACKAGE

&#x20;     ↓

PICKUP ACKNOWLEDGMENT

&#x20;     ↓

WORKING

&#x20;     ↓

RETURNED VERIFIED RESULT



Required principles:



\- baton remains canonical

\- capability remains separate from provider/model identity

\- no worker may select an unrestricted expensive successor

\- dispatch must be auditable

\- dispatch must be idempotent

\- unavailable target remains WAITING\_FOR\_CAPABILITY

\- no fake pickup

\- no fake completion



\---



\# S2E — OFFICE METAPHOR / POLISHED ANIMATION



Goal:

Make the truthful office visually convincing and presentation-ready after its

state mapping and visual verification are stable.



\[ ] S2E — Office metaphor / polished animation



Expected scope:



\- polished rooms

\- character movement

\- believable transitions

\- desk/work states

\- validation-room transitions

\- artifact movement metaphor

\- waiting/dispatch representation

\- visual continuity

\- animation quality

\- refined typography/layout

\- presentation-quality office experience



This stage may improve how truth is represented.



It must never change what the truth is.



\---



\# S3 — AUTONOMOUS MULTI-STAGE OFFICE WORKFLOWS



Future guidance only.



Do not implement until S2 is accepted and Owner + ChatGPT explicitly promote S3.



Goal:

Allow verified tasks to progress across multiple specialist capabilities with

minimal Owner intervention while retaining authority, validation and audit.



\[ ] S3 — Autonomous multi-stage office workflows



Likely concerns include:



\- multi-step task decomposition

\- bounded specialist handoffs

\- explicit repair workflows

\- explicit retry policy

\- dependency waiting

\- escalation

\- human decision gates where required

\- cross-agent verification

\- project-level progress

\- no silent autonomy expansion



Exact S3 subdivision is intentionally NOT fixed yet.



\---



\# S4 — LONG-RUNNING DIGITAL ORGANISATION



Future guidance only.



Do not implement until S3 has been certified and Owner + ChatGPT explicitly

promote S4.



Goal:

Allow AppShak to operate persistent projects over long periods while remaining

observable, recoverable and governed.



\[ ] S4 — Long-running organisation / project operation



Likely concerns include:



\- multiple concurrent projects

\- long-duration state

\- scheduled/triggered work

\- recurring workflows

\- resource/capability availability

\- project-level memory

\- resumability after extended downtime

\- operator notifications

\- archival/recovery

\- governance under prolonged autonomy



Exact S4 subdivision is intentionally NOT fixed yet.



\---



\# CURRENT POSITION



Current certified progress:



S1   Durable truth                         COMPLETE

S2A  Operator interaction / inspection     COMPLETE

S2B  Live office-state projection          COMPLETE

S2C  Visual/perceptual verification        NEXT

S2D  External capability handoff           PENDING

S2E  Office metaphor / polished animation  PENDING

S3   Autonomous office workflows           FUTURE GUIDANCE

S4   Long-running digital organisation     FUTURE GUIDANCE



\---



\# HARD FLOOR



The following baseline must remain recoverable:



Tag:

appshak-s1-certified



Commit:

69d005dccf4023656bc95fa0218a08de72282713



No later visual, UI, dispatch or autonomy work may weaken the certified S1

truth, authority, durability, validation, baton or recovery guarantees.

