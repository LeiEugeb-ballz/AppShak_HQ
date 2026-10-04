# S2D — External capability handoff

Status: **PASS_WITH_NONBLOCKING_FINDINGS** for the bounded, provider-neutral external handoff contract. Work began from clean, synchronized commit `2cd7cf97cecfa9d9b50f0e48515df9d14909a99c`. This certifies a separate local worker process crossing a narrow loopback boundary into durable ATS state; it does **not** claim that a commercial provider is configured, connected, or operating live. [S2C visual verification](S2C_VISUAL_PERCEPTUAL_VERIFICATION.md) remains the preceding accepted stage.

## Authority and data flow

The existing verified runtime baton identifies a completed source owner task, its validation, the next objective, and a required capability. `CapabilityRoutingPolicy` selects a configured target based on capability; provider class, model class, and worker instance remain distinct metadata. The default policy has no targets and persists `WAITING_FOR_CAPABILITY` without an attempt or invented activity.

For a selected target, the trusted backend creates and assigns an owner-approved destination task with `source_request_id=handoff:<dispatch_id>`, the baton objective, the selected target/workspace identity, and a required acceptance criterion. `ExternalHandoffManager.prepare` verifies that contract and applies the existing `ToolPolicy` to the planned external `WRITE_FILE`, including Chief authorization and workspace confinement. It persists `chief_authorized_by` and binds the contract to the existing `baton_dispatches` row. That dispatch ID is the handoff ID; there is no second workflow table. The row retains the source baton, required capability, policy route/version, context reference, destination task, result reference, credential digest, and transition timestamps. `publish` rechecks the same policy and reserves one S1 execution attempt before advertising `HANDOFF_DISPATCHED`; its `external:<dispatch_id>` source request/idempotency key prevents a second attempt.

The backend-only `external_handoff_http` service binds to `127.0.0.1`. It exposes only `/pickup`, `/renew`, and `/result` as authenticated POST operations. It does not expose task creation, routing, dispatch, validation, or completion. The separate `external_worker_demo` process receives a handoff ID and an out-of-band secret through its environment; it receives no SQLite path. Pickup begins the reserved attempt, records `EXTERNAL_PICKUP_ACKNOWLEDGED`, and fences other workers by lease owner/generation. Successful result return checks the fixed workspace path, file existence, size limit, and SHA-256; it then uses `record_attempt_outcome` to create the existing task artifact and advance only to `READY_FOR_VALIDATION`. The existing `ArtifactValidator` independently reads exact bytes and persists PASS/FAIL. Only PASS can move the task to `COMPLETE`.

The credential itself is not stored in source, baton, report, SQLite, projection, or logs. SQLite holds only its SHA-256 digest. A deployment must provision a high-entropy per-handoff secret out of band. The local worker fixture uses a generated secret. Worker identity is fenced by the handoff credential plus an asserted worker ID; this is not a remote individual-identity service. Chief approval is supplied at the trusted backend call site and checked by the existing mechanical policy; the worker cannot call that backend-only operation over HTTP.

## Durable states and restart behavior

`WAITING_FOR_CAPABILITY` has a persisted reason and no fabricated attempt. If a configured target disappears between route and publish, the dispatch returns to waiting. A compatible target must be explicitly available again before publish; no unrelated fallback is used. A prepared but unpublished handoff has no external effect. If the backend crashes after attempt reservation, repeating publish reuses the same attempt. If it crashes after worker pickup but before recording the acknowledgement, reconciliation reconstructs it from the running attempt. If the attempt finishes but the dispatch-row update is interrupted, reconciliation reconstructs the terminal result from durable attempt and artifact evidence.

An expired running lease becomes `NEEDS_RECONCILIATION` / handoff `UNKNOWN`; no new worker automatically retries an uncertain effect. The demo worker uses exclusive file creation and accepts an identical existing file on same-owner replay after a write/response gap. A changed existing file is rejected. A failed worker result moves the owner task to `EXECUTION_FAILED`, not `COMPLETE`. Duplicate terminal delivery of the same result is idempotent; a conflicting result is rejected.

## Observation and operational boundary

`GET /api/office/state` reads the canonical SQLite snapshot and now includes handoff task/attempt linkage, result and payload references, pickup owner/generation, and dispatch/ack/result timestamps and digest. Reads do not advance state. The existing UI remains read-only and no UI file or operational endpoint was changed. S2D exposes backend facts for later presentation; it does not claim that the current office artwork depicts every new state. The worker service and office projection remain separate surfaces.

The trusted backend explicitly prepares and publishes the handoff using the existing baton/task APIs. The worker service can be started against an **existing** mailstore with:

```powershell
python -m appshak_substrate.external_handoff_http --db-path E:\AppShak_HQ\appshak_state\substrate\mailstore.db --port 8011
```

Its startup reconciles active handoffs, never implicitly creates a missing mailstore, and listens on loopback only. The separate demo worker is a deterministic transport/contract fixture, not a production model adapter. Its endpoint is `http://127.0.0.1:8011`; the handoff ID, target ID, worker ID, and out-of-band environment credential must be supplied explicitly. Nothing in S2D auto-launches or selects a commercial model.

## Certification evidence

| Scenario | Evidence | Result |
| --- | --- | --- |
| Golden | Verified source baton → configured capability route → bound task/attempt → separate process pickup/result → independent validation PASS → COMPLETE | PASS |
| No target | Default policy persists waiting reason; no target, attempt, or fake pickup; persists across reopen | PASS |
| Negative validation | External result returns; exact-text criterion fails; task does not complete | PASS |
| Restart | Reopened mailstore retains ack/owner/generation; interrupted terminal update reconciles from attempt/artifact; duplicate attempt prevented | PASS |
| Invalid result | Wrong credential/target, wrong owner/task binding, stale baton, wrong Chief approval, wrong handoff, wrong digest, and unauthorized operational HTTP method rejected | PASS |
| Uncertain effect | Target loss returns to waiting before pickup; expired in-flight lease becomes UNKNOWN without replay | PASS |
| ATS/UI | Read-only projection repeated without state change; existing 32 UI tests include GET-only network checks | PASS |

Focused S2D unittest discovery: **14 passed, 0 failed**. Repository-wide UI lint: **PASS**. `npm run test:office`: **32 passed, 0 failed**. `npm run build`: **PASS**. Full Python regression: **125 passed, 0 failed**. `python -m appshak_substrate.s1_certification`: **PASS**. Chambers A, B, and C: **PASS**. `git diff --check`: **PASS**. The S1 certification runner's fixture remains a waiting-capability scenario; the separate S2D tests certify the external pickup/result path.

## Files and bounded findings

- `appshak_substrate/schema.sql` and `mailstore_sqlite.py`: in-place dispatch-column migration, reusing existing baton/task/attempt records.
- `appshak_substrate/baton_routing.py`: optional configured target workspace; provider/model still policy metadata.
- `appshak_substrate/external_handoff.py`: trusted preparation, publish, pickup, result, and reconciliation contract.
- `appshak_substrate/external_handoff_http.py` and `external_worker_demo.py`: loopback endpoint and separate process fixture.
- `appshak_projection/office_state.py`: read-only canonical handoff fields.
- `tests/test_s2d_external_handoff.py`: 14 focused scenarios.
- `docs/INDEX.md`, the S2D baton/projection, and the single S2D master-plan checkbox: navigation and handover only.

Nonblocking limits: no commercial provider/remote transport was configured or tested; the demo worker is a local text-file adapter; the service is loopback-only and requires explicit trusted backend orchestration; per-worker identity beyond the per-handoff secret is not independently attested; new handoff states are exposed in ATS but no S2E visual treatment was added. The Owner-controlled master-plan CURRENT POSITION table was not changed. No commit, push, or tag is part of this work package.

Next: **S2E — Office metaphor / polished ATS-driven movement**, subject to Owner review. The [S2D handover baton](../.appshak/batons/BATON-0013-s2d-external-handoff.json) is a repository projection only; runtime dispatch authority remains in canonical SQLite.
