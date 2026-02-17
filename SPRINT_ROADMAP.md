# AppShak Stability and Sprint Roadmap

## Acceptance Criteria

1. 24-hour heartbeat stability:
- Kernel heartbeat loop is resilient to runtime exceptions and keeps running.
- Agent supervisors restart agent loops after crashes.
- Safeguard and memory operations are guarded and non-blocking from the heartbeat path.

2. No drift:
- No weighted voting logic is implemented.
- No multi-process logic is implemented.
- Execution authority remains with Chief approval and Kernel-managed lifecycle.

3. Traceability:
- Every published event is written to JSONL logs (`EVENT_PUBLISHED`).
- Every consumed event is written to JSONL logs (`EVENT_CONSUMED`).
- External action pipeline stages are logged: `REQUEST`, `CHIEF_APPROVAL`, `SAFEGUARD_CHECK`, `EXECUTE`, `LOG_RESULT`.
- Agent events are written to isolated namespace logs under `appshak_state/agents/<agent_id>.jsonl`.

## Sprint Sequence

1. Sprint 1:
- EventBus
- BaseAgent
- Kernel
- JSON Persistence

2. Sprint 2:
- Recon logic
- Command arbitration
- Forge pipeline

3. Sprint 3:
- Execution sandbox
- Logging hardening
- Crash recovery tests
