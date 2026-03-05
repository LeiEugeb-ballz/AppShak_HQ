# Module Test-State Snapshot

- Run ID: $runId
- Scope: Automated unittest evidence only

| Module | Tested In This Run | Could Be Tested Next | Current Status |
|---|---|---|---|
| Substrate | Yes (unit/integration coverage in 	ests/) | Live swarm + runtime logs + long-run behavior | PASS |
| Plugins | Yes | Plugin behavior under live queue conditions over time | PASS |
| Projection | Yes | Live projector polling under runtime load | PASS |
| Governance | Yes | Runtime governance replay/hash during burn run | PASS |
| Integrity | Yes (API/logic tests) | Long-horizon report cadence under active runtime | PASS |
| Inspection | Yes (index/timeline tests) | Live entity timeline drift checks | PASS |
| Stability | Partial (logic/tests) | Full 6-hour gate execution | PENDING_RUNTIME |
| Observability | Yes (backend tests) | Live websocket/load behavior in long run | PASS |
| UI | No automated UI test in this run | Manual/automated UI runtime flow checks | DEFERRED |
| Cross-Layer | Partial via integration tests | End-to-end system gate with all services + 6h run | PENDING_RUNTIME |
