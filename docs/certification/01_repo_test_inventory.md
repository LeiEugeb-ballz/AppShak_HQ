# Repository Test Inventory

Planning inventory derived from current `tests/` contents and runtime modules.

## Existing Automated Test Files

1. `tests/test_mailstore_durable.py`
2. `tests/test_supervisor_workers.py`
3. `tests/test_tool_gateway_enforcement.py`
4. `tests/test_plugin_loader.py`
5. `tests/test_intent_engine_plugin.py`
6. `tests/test_kernel_plugins_integration.py`
7. `tests/test_projection_layer.py`
8. `tests/test_observability_backend.py`
9. `tests/test_governance_layer.py`
10. `tests/test_phase4_integrity_and_inspection.py`

## Coverage Mapping by Layer

1. Substrate durability and workers:
   - `test_mailstore_durable.py`
   - `test_supervisor_workers.py`
2. Tool gateway and enforcement:
   - `test_tool_gateway_enforcement.py`
3. Plugin system and intent engine:
   - `test_plugin_loader.py`
   - `test_intent_engine_plugin.py`
   - `test_kernel_plugins_integration.py`
4. Projection layer:
   - `test_projection_layer.py`
5. Observability backend:
   - `test_observability_backend.py`
6. Governance:
   - `test_governance_layer.py`
7. Integrity/inspection/stability (Phase 4):
   - `test_phase4_integrity_and_inspection.py`

## Runtime Validation Areas Not Fully Proven by Unit Tests Alone

1. Long-horizon stability run completion (6h/12h/24h modes).
2. End-to-end live service interoperability (swarm + projector + observability + UI).
3. WebSocket reconnect behavior under prolonged runtime.
4. Artifact continuity and evidence integrity across checkpoint windows.

## Additional Planned Validation Inputs (No New Tests Implemented Here)

1. Full operational runbook execution (separate terminals/processes).
2. Evidence capture checklist completion.
3. Manual UI inspection flow verification.
4. Determinism replay/hash cross-checks with preserved artifacts.
