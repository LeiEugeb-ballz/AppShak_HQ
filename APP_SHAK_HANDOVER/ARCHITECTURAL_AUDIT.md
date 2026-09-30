# SHIFT 1 — Independent architectural audit

Audit status: **CORRECTION_REQUIRED**  
Canonical repository: E:\AppShak_HQ  
Starting commit: a85ab5e15a3d23f864202fd413f4eaf0b5c5d081  
Source baton: [BATON-0001](../.appshak/batons/BATON-0001-repo-state.json)  
Scope: source-level operational architecture; no production execution or corrective implementation.

## Audit basis and limits

BATON-0001 and the [Shift 0 report](REPO_STATE_CONFIRMATION.md) are accepted as the repository handoff. HEAD is the immediately following Shift 0 commit; the tracked working tree was clean at audit start. No alternate repository discovery was performed. The earlier remote-sync statement applies to its recorded checkpoint; Shift 0's local follow-up was not pushed.

Architecture intent was read from README.md, ONBOARDING.md, CURRENT_STATUS.md, and the phase documentation already inspected in this conversation. Claims below are grounded in source, not phase names or certification labels. This is an audit against the supplied office-system objective, not a full constitutional clause-by-clause certification.

The 37 passing unittest results are inherited Shift 0 evidence, not a fresh run in this audit. Test source was inspected. No tests were added or executed: some existing tests create intents, repositories, commits, worktrees, and runtime files. No startup was attempted because the documented worktree startup invokes reset/clean. No database was opened through SQLiteMailStore, whose constructor creates directories/schema. Only the three authorized audit outputs were written.

**Current architecture:** AppShak has a real durable event queue, supervised worker processes, callable filesystem/command tools, and derived observability. Separately, it has a core agent kernel with fixed proposal logic and simulated external actions, a Phase 4 reporting/autonomy loop with deterministic ballots and no-op/report actions, and a stochastic office experiment. These are not a complete persistent autonomous office. The shortest path is to connect and harden the substrate around a bounded task/attempt/validation contract, retaining the existing projection and governance modules.

## 1. What actually exists

Paths in this report are relative to the canonical root. Symbols identify the relevant implementation.

| Responsibility | Classification | Source and operational finding |
|---|---|---|
| 1. Supervisor/orchestration | IMPLEMENTED | appshak_substrate/supervisor.py: Supervisor.run/start/_monitor_workers/_spawn_worker. Starts OS processes, checks heartbeats, restarts with backoff. It does not plan or allocate capabilities. |
| 2. Agent lifecycle | IMPLEMENTED | worker_process.py: _main/_build_runtime; supervisor.py: WorkerState. Each named agent is the same AgentRuntime handler with a different ID. Core AppShakKernel._run_agent is a separate asyncio lifecycle. |
| 3. Task/work representation | PARTIAL | types.py: SubstrateEvent; schema.sql: events. Event type/payload/target/correlation/status represent deliveries. No authoritative office task, project, acceptance criteria, or attempt state machine. appshak_office/sprint_arena.py: Task/run_sprint_cycle are simulation data, not that missing store. |
| 4. Dispatch/routing | PARTIAL | SQLiteMailStore._try_claim_next filters target_agent and orders IDs. AgentRuntime.handle_event switches on event type. No capability matching, owner-objective decomposition, or next-stage dispatcher. |
| 5. Deterministic execution | IMPLEMENTED | tool_gateway.py: ToolGateway.execute/_execute_allowed invokes real subprocesses and file I/O. RUN_CMD, WRITE_FILE, READ_FILE, GIT_COMMIT, GIT_DIFF exist; OPEN_PR explicitly denied as unimplemented. Execution is real; completion semantics are incomplete. |
| 6. Filesystem/worktrees | PARTIAL | workspace_manager.py: WorkspaceManager.ensure_worktrees creates Git worktrees; ToolPolicy.resolve_path confines explicit file requests. Startup also resets/cleans existing workspaces; commands are not OS-sandboxed. |
| 7. Persistence | IMPLEMENTED | mailstore_sqlite.py and schema.sql; memory.py: GlobalMemory; projection/view_store.py; governance/registry.py and ledger.py; phase4/runtime/stability.py. Durable mechanisms exist, with important scope limits below. |
| 8. Event/history | IMPLEMENTED | SQLiteMailStore.append_event/append_tool_audit; supervisor._log_json; GlobalMemory.append_global_log. Event delivery status mutates in place; not every transition has a separate immutable history record. |
| 9. Memory | PARTIAL | GlobalMemory.load_state/_persist_state stores namespaces and kernel snapshots; IntentStore stores intent strings; StabilityRecoveryWrapper stores cycle memory. These are not connected to a live reasoning worker's verified project context. |
| 10. Inter-agent communication | PARTIAL | SQLite target_agent, DurableEventBus, TOOL_RESULT reply_to. Cross-worker messages are possible; command's generic handler merely consumes TOOL_RESULT. No task delegation/acceptance protocol. |
| 11. Validation | DISCONNECTED | tests/, CERTIFICATION_HARNESS.validate_evidence, Phase4 SnapshotValidator.validate, governance replay and integrity functions validate infrastructure/report data. No validator gates each worker artifact or task completion. |
| 12. Retry/repair | PARTIAL | Supervisor._schedule_restart_or_disable; expired mail leases; AutonomyLoopEngine._route_retry; SafeguardMonitor.record_attempt. Process retries and reporting-cycle retries exist; failed business work has no persisted repair workflow. |
| 13. Model/provider routing | NOT IMPLEMENTED | No active provider adapter/call or capability policy found in appshak*, excluding archival source. Historical Halo/ollama_client.py: generate uses a fixed Ollama endpoint/model; not imported into the active runtime. |
| 14. Governance/authority | PARTIAL | ToolPolicy.validate gates on agent_id/authorized_by strings; ChiefAgent approval checks fields; GovernanceEngine/BoardroomArbitrator compute decisions and optionally persist audit. No trusted approval binding from governance to queued tool requests. |
| 15. Observability | IMPLEMENTED | observability/server.py: create_app/build_standalone_app; broadcaster.py: ObservabilityBroadcaster. Read-only snapshots, WS, inspection/integrity/stability endpoints. Standalone wiring lacks the durable event bus. |
| 16. Frontend projection | IMPLEMENTED | appshak-ui/src/main.jsx, App.jsx, SummaryView, OfficeView; hooks and OfficeAnimator render backend-derived telemetry and fixed visual metaphors. Not an owner task-control UI. |
| 17. Artifact handling | PARTIAL | ToolGateway writes files/captures stdout, SQLite stores audit/results; InspectionIndexStore and IntegrityReportStore version report artifacts. No canonical work-artifact registry binding output hash, task, attempt, validator, and Git state. |
| 18. Failure handling | PARTIAL | worker_process._main marks thrown exceptions FAILED; ToolGateway catches execution exceptions and returns denial; kernel heartbeat catches/reports errors. Returned failure is usually acknowledged DONE by the worker. |
| 19. Restart/recovery | PARTIAL | SQLite leases can redeliver unacknowledged events; supervisor replaces dead processes; JSON memory/cycle loaders reload state. No atomic effect/result/ack recovery or preserved worktree guarantee. |
| 20. Autonomous continuation | PLACEHOLDER | run_swarm provides continued polling/liveness; core scout reports idle_scan_complete; Phase 4 repeatedly proposes READ_ONLY_REPORT/NOOP. No connected objective → real artifact → validation → next capability loop. |

Substrate paths above refer to appshak_substrate/; abbreviated projection, observability, governance and phase4 paths refer to their appshak_* packages.

## 2. One concrete work-unit flow

This is a code trace of the supported TOOL_REQUEST path, not a claim that a live job was executed during the audit. The configured live database is absent. An externally supplied request can run a real permitted command or write a file.

| Transition | Classification | Exact implementation and result |
|---|---|---|
| Owner objective → concrete action | HUMAN-DECIDED | Currently an external caller must construct the action, target, workdir, authorization label and idempotency key. No owner submission/translation endpoint in observability/server.py or run_swarm.main. |
| Caller → stored message | DETERMINISTIC | Supervisor.publish_event → SQLiteMailStore.append_event inserts SubstrateEvent(type=TOOL_REQUEST, target_agent=forge, correlation_id, payload.request) as PENDING. |
| Stored message → worker | DETERMINISTIC | worker_process._main → claim_next_event/_try_claim_next: BEGIN IMMEDIATE, oldest eligible ID, lease, CLAIMED. |
| Worker → tool | DETERMINISTIC | AgentRuntime._handle_tool_request fills defaults, then ToolGateway.execute validates workdir/policy/key and reserves the key. |
| Tool → external effect | DETERMINISTIC | ToolGateway._execute_allowed: subprocess.run(shell=False), write_text/read_text or Git subprocesses. This executes supplied instructions; no model plans them. |
| Effect → captured result | DETERMINISTIC | stdout/stderr/return_code or exception, then set_idempotency_result and append_tool_audit in separate operations. File output remains on disk. |
| Result → reply | DETERMINISTIC | AgentRuntime appends TOOL_RESULT targeted to reply_to or command, with source_event_id, allowed, return_code, output and audit_event_id. |
| Handler return → delivery status | DETERMINISTIC | worker_process._main ignores the returned dictionary and calls ack_event. Denied tools, invalid requests and nonzero command exits can therefore produce DONE delivery status. A raised uncaught exception produces FAILED instead. |
| Reply → next work stage | DETERMINISTIC | command uses AgentRuntime's generic processed return; it does not validate output, repair a failure or dispatch a successor. This is a breakpoint. |
| Output → validated task success | UNKNOWN | No such transition exists. DONE means delivery handling completed, not accepted work. |
| SQLite → persisted view | DETERMINISTIC | ProjectionProjector.project_once counts events, PENDING non-control messages and tool authorization outcomes; ProjectionViewStore.save uses replace. |
| View → UI | DETERMINISTIC | standalone server loads view.json; /api/snapshot emits four fields, WS view_update can include the larger view; React hooks render them. This is telemetry, not a task verdict. |

No MODEL-DECIDED transition exists in this real tool path. No SIMULATED transition is needed to execute the supplied tool. Simulation occurs in the alternative core and office paths, not in subprocess/file execution.

Breakpoints: absent objective intake/planning; no task identity/state contract; no authenticated Chief decision binding; completion independent of validation; no task-aware TOOL_RESULT consumer; non-atomic effect/result/reply/ack; no output registry. On restart, stored events, results and files can survive, but ambiguous execution and startup workspace cleanup prevent an end-to-end recovery guarantee.

Additional disconnected path: AppShakKernel._route_event handles PROPOSAL and EXTERNAL_ACTION_REQUEST only. Chief arbitration publishes PROPOSAL_DECISION, but no routing branch connects that decision to BuilderAgent.translate_proposal_to_plan/prepare_external_action_request. The injected tool_gateway is stored but never invoked by the kernel. SafeguardMonitor.execute_in_sandbox only permits SIMULATE/NOOP.

## 3. Persistence reality

Read-only existence checks found appshak_state/ and appshak_state/substrate/mailstore.db **ABSENT**. Therefore there are no live database rows, JSON state snapshots or restart contents to inspect at these configured locations. No store was created. .appshak contains the committed baton and an existing intents.json; its private contents were not printed.

The table classifies implementation durability when each component is used, not presence of a populated live deployment.

| Entity | Classification | Authoritative mechanism and limits |
|---|---|---|
| Agents | PARTIALLY_DURABLE | worker_heartbeats records last PID/consumer/time; governance registry JSON can store definitions/trust. Process handles, active selection, disable/restart budgets are reconstructed or in memory. |
| Tasks | ABSENT | No office-task store. Events and simulated sprint tasks are not a canonical work contract. |
| Task status | ABSENT | events.status is delivery state, not validated task state. |
| Messages | DURABLE | schema.sql events.payload_json/target_agent/correlation_id; SQLiteMailStore. |
| Events | DURABLE | SQLite events with WAL/FULL; global JSONL logs in separate core runtime. Event status is mutable. |
| Artifacts | PARTIALLY_DURABLE | Real filesystem outputs, Git commits if requested, tool_audit results and versioned report files. No durable task/hash/validation registration; workspace cleanup can destroy uncommitted output. |
| Decisions | PARTIALLY_DURABLE | GovernanceAuditLedger JSONL and core external_actions.jsonl/Phase4 traces when those paths run. Substrate approval label is not linked to these decisions. |
| Work ownership | PARTIALLY_DURABLE | target_agent and leases preserve delivery ownership until expiry; no project/task/attempt owner record or fencing generation. |
| Validation results | PARTIALLY_DURABLE | Integrity/inspection reports and historical certification evidence persist; no per-task acceptance verdict store. |
| Failure state | PARTIALLY_DURABLE | events.error/status, tool audit/results, JSON logs. Supervisor disabled set is ephemeral; returned tool failure may coexist with DONE. |
| Retry state | PARTIALLY_DURABLE | Leases persist; separate Phase4 state.json stores retry_queue and executed_keys. Supervisor backoff/counts and safeguard counters are ephemeral; FAILED mail is not automatically repaired. |
| Model handoffs | PARTIALLY_DURABLE | Committed BATON-0001 is durable handoff documentation. No runtime registration, verification, transactional successor trigger or consumption receipt. |
| Project state | PARTIALLY_DURABLE | Git and baton capture source/checkpoint context; GlobalMemory persists kernel namespaces. No canonical owner-objective/task/artifact project ledger. |

Concrete stores/schemas:

- SQLite: appshak_substrate/schema.sql defines events, leases, tool_audit, idempotency_keys, worker_heartbeats. mailstore_sqlite.py initializes it and handles transactions. No tasks/artifacts/validations/batons tables.
- Core memory: appshak/memory.py writes memory_store.json, agents/*.jsonl and logs/*.jsonl under configured memory_root. _persist_state uses direct write_text, not atomic replace; malformed JSON load returns existing/default state.
- Projection: appshak_projection/view_store.py atomically replaces view.json; missing/corrupt JSON yields defaults. A projection is not execution authority.
- Governance: AgentRegistryStore.save_atomic, GovernanceAuditLedger.append/reconstruct_registry/validate_hash_chain. File appends, registry writes and execution are not one transaction.
- Phase4: StabilityRecoveryWrapper persists state.json, memory.json and cycle_trace.jsonl under appshak_state/phase4/runtime. ExternalActionGate appends external_audit.jsonl separately. Completed-cycle and executed-key histories are bounded.
- IntentStore.load_intents resets missing/malformed content to a default intent; it does not preserve a corrupted objective record for diagnosis.

SQLite durability is real. It does not establish exactly-once side effects or durable task continuation.

## 4. Autonomy reality

The supplied command enters run_swarm.main, optionally ensures three Git worktrees, constructs Supervisor, spawns three worker_process processes, emits start/heartbeat/control events, polls process health, and terminates after 1200 seconds. --durable is parsed but SQLite is used regardless. The command does not inject an owner task, start AppShakKernel, load the intent plugin, start Phase4Runner, call a model, or launch the projector/UI.

| Claimed activity | What this command actually supplies |
|---|---|
| Receive work | Yes, externally inserted events targeted to an agent; unrouted messages excluded by default. |
| Decide next actions | No model or task planner. Fixed event-type dispatch only. |
| Execute tools | Yes for TOOL_REQUEST and forge's FORGE_PROPOSE_CHANGE. |
| Exchange work | Reply messages exist; business delegation/acceptance does not. |
| Persist results | Tool audit and TOOL_RESULT persist, independent of delivery acknowledgment. |
| Resume | Expired claimed messages become eligible; not a resumable multi-step task. |
| Validate peers | No connected validator. |
| Recover failure | Worker process restarts; not durable repair of rejected/failed work. |

Alternative activity is explicitly distinguishable:

- Core ScoutAgent.search_for_problems emits idle_scan_complete; BuilderAgent returns fixed strings; ChiefAgent checks presence of fields. SafeguardMonitor reports sandbox simulation success.
- Phase4 AutonomyLoopEngine._run_scout proposes READ_ONLY_REPORT or NOOP. BoardroomExecutionLayer._build_ballots computes scores from queue/running/stress counters, not model judgments. ExternalActionGate.execute records an executed result and payload digest but does not invoke ToolGateway or perform the requested external work. The pipeline does write real inspection/integrity reports.
- appshak_office/worker_profiles.py: WorkerProfile.sample_outcome samples success, delay and rework with Random. SprintArena.run_sprint_cycle persists statistics from those outcomes. This is an explicit experiment, not evidence of real engineer delivery.

## 5. UI reality

| Display/source | Classification | Interpretation |
|---|---|---|
| Summary running/queue/current event/time | REAL STATE | useSnapshot → /api/snapshot → projection file, subject to freshness and defaulting. current_event is the latest appended event, not necessarily executing work. |
| Allowed/denied tool counts, worker events | REAL STATE | SQLite-derived view via projector; full fields via WS view_update. Allowed counts authorize execution; they do not count validated success. |
| Inspection timelines, integrity and stability | REAL STATE | useInspectionData → stored report/index endpoints. Real report data can itself be based on synthetic or historical inputs; provenance matters. |
| Stress, lighting, avatar motion, pulses | DERIVED STATE | OfficeAnimator.ingestView/normalizeIncomingView and effects.js map counters/events to animation. |
| Four avatars, office zones, colors | STATIC/MOCK DATA | Fixed AVATAR_IDS, OFFICE_ZONES and colors. Their presence does not prove a worker is alive. |
| Initial false/zero/default timestamps | STATIC/MOCK DATA | Hook/server fallbacks; not proof of an observed empty workload. |
| Validated task completion or actual owner objectives | UNKNOWN | No authoritative task/acceptance data supplied to these views. |

Material wiring limits:

1. server.build_standalone_app discards mailstore_db. _ProjectionStateView has no kernel/event bus, so ObservabilityBroadcaster has no mail_store for its durable poll loop. Dedicated tool/restart streams tested with an injected DurableEventBus are not the documented standalone configuration. Full projection updates still work.
2. SnapshotResponse exposes only running, event_queue_size, current_event, timestamp. OfficeView's richer counters depend on WS. Polling cannot restore every full-view field after missed WS updates.
3. useProjectionView marks success when any payload arrives, independent of projection age. /api/health always says ok. A responsive API serving stale view.json is not proof of a healthy swarm.
4. ProjectionProjector counts PENDING, not CLAIMED work; running follows start/stop events and may remain true after an abrupt supervisor death. Frontend animations react to event-type changes and do not constitute lossless event replay.

Shift 0 recorded only that the UI build was not executed; it did not record a technical failure or a reason. It would be false to invent one. Current node_modules is absent; Node v24.16.0 and npm 12.0.1 are available; package.json, package-lock.json, src/main.jsx and Vite configuration are present. No obvious architectural compilation blocker was found by static inspection. Build remains UNVERIFIED. Installing dependencies/building would write outside the three allowed outputs, so this audit did not do so. The runtime contract gaps above are distinct from build failure.

## 6. Baton integration

The concept fits the existing event/SQLite/projection architecture, but presently it is a human-produced Git-tracked handoff.

Reusable mechanisms: SubstrateEvent JSON payload plus correlation_id/target_agent; SQLiteMailStore transaction/lease mechanics; tool audit/idempotency tables; inspection/integrity artifacts; Git checkpoint IDs; atomic JSON projection writers. A validated-stage event could carry a baton ID and required capability.

Supervisor currently manages fixed agent IDs and liveness; it has no capability registry or dispatch policy. Add a small deterministic dispatch service beside it, not model selection inside Supervisor._monitor_workers.

Minimal proposed integration, not implemented:

- Canonical task/attempt, validation and baton records with version/status constraints in the existing persistence layer.
- A verified-stage transition transaction inserting the baton metadata and a unique successor event/outbox record. Delivery claims must record which baton/version was consumed.
- Evidence references containing task/attempt IDs, immutable relative artifact paths, hashes, validator result, source commit, worktree/output commit or diff hash, and policy version. Git HEAD alone cannot describe uncommitted output.
- Deterministic evidence verification before acceptance. A hash proves identity, not correctness; a model's declaration of success is not the verdict.
- Retain immutable JSON baton exports for human/tool interoperability. CURRENT_BATON.json should eventually be a rebuildable atomic projection of a canonical accepted baton, not an independent mutable authority.
- Database commit and filesystem write are not one transaction. Use an outbox/projector with replay/reconciliation and explicit incomplete-export status; never claim atomicity across SQLite, Git and files.
- Compare-and-set task/baton version, bounded attempts, escalation, and policy-authorized next capability. No automatic fallback to a more costly route based on model text.

The existing two baton files remain useful. No automated runtime reads of CURRENT_BATON or successor dispatch were found.

## 7. Model routing

Active workers do not call a model. The only located provider client is the preserved stashed_instances_2026-02-19/Halo/ollama_client.py: generate, with a fixed local Ollama URL and model string; explorer.py and critic.py import it in that historical experiment. It is not current routing.

Capability classes REPOSITORY_INSPECTION, ROUTINE_EXECUTION, IMPLEMENTATION, INTEGRATION, ARCHITECTURAL_AUDIT, VALIDATION and ROOT_CAUSE_ANALYSIS can be policy keys without changing core task identity. Persist required capability, policy version, selected adapter identifier, bounded resource authorization and attempt evidence. Resolve the available model through configuration behind an adapter. An unavailable route should block/escalate explicitly; routine tools and deterministic validation need not call models.

Models may propose plans, repairs or capability needs. Deterministic policy must decide dispatch, tool authorization, acceptance, attempt limits and spending constraints. Existing constitutional no-spending constraints must remain in force; this audit grants no provider use or budget. No particular model is recommended or changed.

## 8. Minimum office vertical slice

| Responsibility | Existing match | Status |
|---|---|---|
| Owner | IntentStore strings and external publish_event callers; no owner task interface | NEEDS SMALL IMPLEMENTATION |
| Supervisor | Real process supervision and targeted mailbox | EXISTS |
| Engineer | AgentRuntime + ToolGateway can carry out supplied actions; no reasoning adapter/planner | NEEDS SMALL IMPLEMENTATION for one bounded worker adapter |
| Real execution | Whitelisted commands/file actions | EXISTS, reliability/authority corrections required |
| Artifact | Files, tool audit/stdout, report stores | NEEDS SMALL IMPLEMENTATION for task-bound artifact registration |
| Validator | Existing unittest/commands and integrity/replay functions | NEEDS CONNECTION plus a persisted per-task verdict gate |
| PASS / REPAIR / FAIL | Message DONE/FAILED and disconnected cycle retry | NEEDS SMALL IMPLEMENTATION of task/attempt transitions |
| Persisted history | SQLite + governance/report JSON stores | NEEDS CONNECTION through one work identity |
| Automatic next capability | Static baton files only | NEEDS SMALL IMPLEMENTATION of dispatch policy and handoff acceptance |

The complete slice does not exist. No evidence requires replacing the event bus, SQLite, React, or governance model. These are assessments for one constrained task type with explicit acceptance, not a claim that a general autonomous engineering organization is a small feature.

## 9. Material findings

P0 means a blocker to the requested reliable slice, not a claim of production outage.

### P0 — four findings

**P0-01: Default worktree startup discards unfinished output.** workspace_manager.py: ensure_worktrees executes reset --hard and clean -fd even when the path already exists and reset_on_ensure is false. _ensure_clean may also clean -fdx. A restart using the documented command can destroy uncommitted/untracked work and ignored output. Comment wording about first creation does not restrict the branch.

**P0-02: No authoritative task completion/validation lifecycle.** schema.sql has delivery state only; worker_process._main unconditionally acknowledges returned results; AgentRuntime accepts unknown messages with processed and consumes TOOL_RESULT without a validator. ToolGateway allowed=true can accompany a nonzero exit code. No owner → artifact → independent verdict transition protects factual completion.

**P0-03: Side effects and durable outcomes can diverge across crashes.** ToolGateway.execute reserves a key before execution, then separately writes the result and audit; AgentRuntime separately publishes reply and worker separately acks. Crash after reservation can block work never executed; crash after effect but before recording loses proof. A replay receives duplicate denial instead of a recovered result. payload.allow_duplicate bypasses key reservation. This is duplicate suppression, not exactly-once recoverable execution.

**P0-04: Long valid work conflicts with liveness and leases.** worker_process._main refreshes heartbeat only between synchronous handle_event calls. Gateway timeout defaults to 120 seconds; supervisor effective default heartbeat timeout is 8 seconds and lease 15 seconds. A longer command can be killed as unresponsive; a lease can expire during a side effect, allowing redelivery. No in-flight renewal/fencing or child-process-tree lifecycle protocol exists. Evidence: worker_process._main, Supervisor._heartbeat_missing/_monitor_workers, SQLiteMailStore._release_expired_leases_locked.

### P1 — five findings

**P1-01: Approval labels and command prefixes are not a trusted authority boundary.** ToolPolicy.validate trusts request.authorized_by == command; no linked approved decision is checked. AgentRuntime preserves supplied request fields via setdefault. RUN_CMD checks prefixes, not argument semantics or an OS sandbox: Git options and tests can access outside a workdir or execute arbitrary test code. This must be constrained before model-supplied actions are admitted.

**P1-02: Durable core-kernel integration is incomplete.** AppShakKernel.heartbeat retrieves durable messages but never calls ack_event/fail_event/requeue_event; claimed work can be delivered again after expiry. _route_event does not connect proposal decisions to Builder or the injected gateway. The compatibility bus without target_agent can compete for targeted messages if launched on the same DB as workers. These alternate paths cannot simply be launched together to obtain an office.

**P1-03: Model work and baton dispatch are absent from the active loop.** No active capability/provider adapter, verified stage acceptance, durable successor trigger or consumption receipt. Current handover requires a human or external agent to select and start the next stage. This blocks autonomous continuation, though supplied deterministic tool work remains possible.

**P1-04: Telemetry is not a dependable work-success/liveness signal.** Standalone server drops mailstore wiring; API health ignores stale input; event/audit counters and animated success cues do not prove validated work. No task truth is projected. See section 5.

**P1-05: JSON recovery can silently erase the distinction between missing and corrupt state.** GlobalMemory writes directly and returns defaults on bad JSON; IntentStore can overwrite malformed intent data with defaults; Phase4 StabilityRecoveryWrapper also defaults on load errors. Phase4 prepare_cycle writes in-flight state, while run_cycle subsequently saves its earlier loaded state; cycle identity includes snapshot timestamp. Together with separate audit/state writes, this is not a demonstrated crash-safe resume protocol. Preserve corruption evidence and reconcile before trusting autonomous continuation.

### P2 — three findings

- **P2-01: Reproducible continuation setup is incomplete.** Root Python package/lock manifest is absent; dependencies are prose guidance. UI has a lockfile but no build verification here. State formats and operator execution steps need versioned documentation with the new bounded slice.
- **P2-02: Reporting scale/replay limits.** Projector lists all events on each pass, fetches a bounded recent audit window, and broadcaster/client buffers are finite. Appropriate for a bounded slice; not an unlimited audit-history transport.
- **P2-03: Phase4 reporting/autonomy limits are not business-work proof.** Bounded executed/completed key retention, post-cycle timeout detection, fabricated reasoning scores and NOOP/report actions must remain scoped as such. Do not expand this path merely to make the slice look autonomous.

P3: none raised. Cosmetic cleanup, archive deletion, naming changes and framework migration are outside this audit.

## 10. Test reality

Shift 0 ran 37 cases successfully. Source inventory: governance 8; intent/store 5; kernel plugin integration 2; mailstore 1; observability 5; integrity/inspection 6; plugin loader 1; projection 7; supervisor 1; gateway/worktree 1.

| Guarantee | Existing coverage | Important limit |
|---|---|---|
| Persistence/restart | TestMailstoreDurable.test_publish_consume_crash_recovery_no_duplicates; registry save/replay; projection round-trip | Mailstore test leaves one lease unacked and sleeps, using the same store; no effect-crash reconciliation or whole-office restart. |
| Task transition integrity | No office-task test | Delivery states and worker UI transitions do not test task acceptance rules. |
| Duplicate execution | Gateway rejects a repeated git status key; lease test verifies unique acked IDs | No crash between reservation/effect/result; allow_duplicate and ambiguous effects untested. |
| Worker failure | TestSupervisorWorkers kills forge and sees restart plus 30 DONE TEST_ROUTED_EVENT messages | Generic handler events, not long-running real tools or artifacts. |
| Validation failure | Intent plugin emits PROPOSAL_INVALID; snapshot normalization and report assertions | No validator-rejects-artifact → repair/fail flow. Plugin tests do not prove that invalidation stops core arbitration. |
| Retry behavior | Worker restart observed; lease reclaim observed | No persistent budget, exhausted repair workflow, or supervisor restart restoration. |
| Model/tool failure | Missing plugin import handled; policy denial/traversal tested | No active model failure tests; no subprocess timeout/nonzero result-to-task-failure coverage. |
| Worktree isolation | Gateway test creates worktrees, blocks path traversal | Does not seed dirty existing workspaces and restart ensure_worktrees; no command escape or project recovery test. |
| Projection consistency | Seven cases cover cursor/counts, worker states, stress, atomic save/load | No task outcome projection, stale/dead runtime truth, or full standalone UI integration. |
| Event ordering | IDs/claim order and projection cursors exercised; deterministic governance replay | No cross-producer business causality, outbox ordering or lease-fencing test. |
| Restart/resume | Limited delivery recovery and worker replacement | No owner task/artifact/validator/baton resume or durable-kernel ack test. |
| Corrupt state | Invalid API model payload normalization | No corrupted SQLite/JSON recovery or fail-closed intent/task load test. |

Integrity/inspection tests use synthetic projection/governance data. The test module's Phase4 name does not establish coverage of appshak_phase4/runtime/AutonomyLoopEngine. Existing full certification code validates operational evidence; it does not supply the missing per-task validator.

## 11. Smallest bounded corrective sequence

Recommended next capability: **RUNTIME_STABILIZATION**. Reuse existing services; no implementation is authorized by this audit. Each package below leaves a usable bounded increment and must preserve existing tests/history.

### S1-WP1 — Preserve workspaces and bind execution authority

- OBJECTIVE: Make worker setup non-destructive by default; constrain a single supported worker action route to a recorded trusted approval.
- WHY: P0-01 and P1-01 would otherwise endanger both existing output and new model-originated work.
- FILES/SUBSYSTEMS: appshak_substrate/workspace_manager.py, policy.py, agent_runtime.py, tool_gateway.py; targeted regression tests.
- DEPENDENCIES: None.
- ACCEPTANCE TEST: Existing tracked edits, untracked artifacts and ignored output survive repeated setup; explicit reset is separate. Forged approval labels and out-of-scope command/path variants fail; approved bounded action still runs.
- ESTIMATED COMPLEXITY: MEDIUM.

### S1-WP2 — Make execution attempts recoverable

- OBJECTIVE: Separate worker liveness from long execution; renew/fence leases; track reserved/running/completed/failed/uncertain effects and recover recorded results.
- WHY: P0-03/P0-04 prevent reliable work, even before a model is added.
- FILES/SUBSYSTEMS: worker_process.py, supervisor.py, mailstore_sqlite.py, schema.sql, tool_gateway.py; child process lifecycle and bounded failure tests.
- DEPENDENCIES: S1-WP1.
- ACCEPTANCE TEST: A permitted action longer than heartbeat/lease thresholds finishes once without spurious worker kill. Crash injection at reservation/effect/result/reply boundaries produces one recoverable result or explicit uncertain/escalated state, never false success or blind repeat. Nonzero exit and timeout are recorded distinctly; duplicate override cannot be supplied arbitrarily.
- ESTIMATED COMPLEXITY: LARGE.

### S1-WP3 — Add one durable owner-task contract

- OBJECTIVE: Add bounded owner intake and task/attempt/status/ownership records with conditional transitions, durable retry limits and transactional dispatch.
- WHY: P0-02; message acknowledgment cannot stand in for business completion.
- FILES/SUBSYSTEMS: Existing substrate schema/store, types.py, agent_runtime.py; a thin owner command/interface and deterministic dispatcher beside Supervisor.
- DEPENDENCIES: S1-WP2.
- ACCEPTANCE TEST: Submit one explicit objective with allowed scope and acceptance command; restart preserves identity/owner/attempt. Returned denial/nonzero tool result cannot mark task passed. Duplicate submission/claim cannot create competing accepted attempts; exhausted retries stop/escalate.
- ESTIMATED COMPLEXITY: MEDIUM.

### S1-WP4 — Gate artifacts with persisted validation

- OBJECTIVE: Register a bounded real output with hashes/Git binding and a separate validator verdict; implement PASS / bounded REPAIR / FAIL.
- WHY: Completes deterministic truth for the minimum slice before automatic model continuation.
- FILES/SUBSYSTEMS: ToolGateway results, task store, existing test-command execution; thin validation adapter using current report/hash utilities.
- DEPENDENCIES: S1-WP3.
- ACCEPTANCE TEST: A worker writes a real artifact; validator rejects an incorrect version, accepts a corrected version, and stores both verdicts/evidence. Tampering invalidates the evidence. Restart after execution but before validation resumes validation; a model success string never passes the task.
- ESTIMATED COMPLEXITY: MEDIUM.

### S1-WP5 — Connect capability routing and verified batons

- OBJECTIVE: Add one configured worker/model adapter behind a capability policy and export/consume verified stage batons from canonical task state.
- WHY: P1-03; enables bounded handoff without conversation copying or hardcoded successor model names.
- FILES/SUBSYSTEMS: Dispatcher, task/event store and outbox; adapter interface; .appshak baton export/pointer projection. Reuse existing provider intent only through explicit configuration; no provider migration.
- DEPENDENCIES: S1-WP3, S1-WP4.
- ACCEPTANCE TEST: Accepted stage atomically schedules one successor capability; duplicate delivery/restart cannot schedule it twice. Export interruption rebuilds CURRENT_BATON. Wrong commit/evidence/version is rejected. Unavailable route, exhausted budget or unauthorized escalation blocks explicitly. A deterministic fixture adapter proves plumbing; one separately authorized configured adapter must perform a bounded real task before claiming model autonomy.
- ESTIMATED COMPLEXITY: MEDIUM.

### S1-WP6 — Project the verified slice and certify restart

- OBJECTIVE: Expose task/validation/baton truth and freshness through existing API/UI; record reproducible setup and one restart/repair acceptance run.
- WHY: P1-04/P1-05/P2-01; the next operator must distinguish idle, stale, failed and accepted work without reconstructing chats.
- FILES/SUBSYSTEMS: ProjectionProjector, observability server/models/broadcaster, current UI hooks/views, state-load error handling and dependency/setup documentation.
- DEPENDENCIES: S1-WP4, S1-WP5.
- ACCEPTANCE TEST: Owner objective → real output → deliberate validation failure → repair → pass → next capability survives process restart. UI shows authoritative verdict and stale/offline state correctly; corrupted canonical state produces an explicit failure. Tests/build and evidence hashes are recorded with source commit and repeatable dependency setup.
- ESTIMATED COMPLEXITY: MEDIUM.

The core-kernel compatibility path from P1-02 must either receive its own acknowledgment/routing correction before reuse or remain explicitly outside this bounded substrate slice. Running both consumers against one mailbox without ownership design is not an integration strategy.

## 12. Handoff and closeout

Audit: CORRECTION_REQUIRED. The architecture is not blocked: useful mechanisms already exist. Repository readiness from Shift 0 remains valid for beginning corrective engineering; it is not a runtime-autonomy certification.

Only authorized outputs:

- APP_SHAK_HANDOVER/ARCHITECTURAL_AUDIT.md
- .appshak/batons/BATON-0002-architecture-audit.json
- .appshak/CURRENT_BATON.json

BATON-0001 remains unchanged. No production source, tests, schemas, dependencies or runtime data were modified; no commits/pushes were made.

Closeout verification: both JSON files parse; all required BATON-0002 fields and existing-source evidence paths validate; the pointer resolves to BATON-0002. HEAD remains the starting commit. Git reports only the tracked CURRENT_BATON change and the new report; BATON-0002 exists but is ignored by the existing .appshak/ rule. It is local and uncommitted, not part of Git history. No staging or ignore-rule change was performed.

Current baton: E:\AppShak_HQ\.appshak\batons\BATON-0002-architecture-audit.json  
Next capability: RUNTIME_STABILIZATION, beginning with S1-WP1.  
Implementation has not begun.
