from __future__ import annotations

import subprocess
import time
from typing import Any, Dict, List, Mapping

from appshak_integrity.utils import canonical_hash

from appshak_phase4.adapters import projection_to_phase4_snapshot
from appshak_phase4.orchestrator import Phase4Orchestrator

from .action_gate import ExternalActionGate
from .boardroom import BoardroomExecutionLayer
from .optimization import SelfOptimizationHook
from .stability import StabilityRecoveryWrapper


class AutonomyLoopEngine:
    def __init__(
        self,
        *,
        orchestrator: Phase4Orchestrator | None = None,
        boardroom: BoardroomExecutionLayer | None = None,
        action_gate: ExternalActionGate | None = None,
        stability: StabilityRecoveryWrapper | None = None,
        heartbeat_seconds: float = 15.0,
        max_retries: int = 2,
    ) -> None:
        self.orchestrator = orchestrator or Phase4Orchestrator()
        self.stability = stability or StabilityRecoveryWrapper()
        self.boardroom = boardroom or BoardroomExecutionLayer()
        self.action_gate = action_gate or ExternalActionGate(root=self.stability.root)
        self.optimizer = SelfOptimizationHook(self.stability)
        self.heartbeat_seconds = _clamp_heartbeat(heartbeat_seconds)
        self.max_retries = max(0, int(max_retries))

    def run_cycle(
        self,
        *,
        replay_snapshot: Mapping[str, Any] | None = None,
        replay_path: str | None = None,
    ) -> Dict[str, Any]:
        started = time.monotonic()
        snapshot = self.orchestrator.extractor.get_snapshot(
            replay_snapshot=replay_snapshot,
            replay_path=replay_path,
        )
        phase4_snapshot = projection_to_phase4_snapshot(snapshot)
        state = self.stability.load_state()
        cycle_index = _as_int(state.get("next_cycle_index"), default=1)
        cycle_id = _derive_cycle_id(phase4_snapshot=phase4_snapshot, cycle_index=cycle_index)
        cycle_timestamp = phase4_snapshot.timestamp
        prep = self.stability.prepare_cycle(cycle_id=cycle_id, cycle_index=cycle_index)

        if not prep.allowed:
            return {
                "cycle_id": cycle_id,
                "cycle_index": cycle_index,
                "timestamp": cycle_timestamp,
                "status": "skipped_duplicate",
                "reason": prep.reason,
                "heartbeat_seconds": self.heartbeat_seconds,
            }

        event_log: List[Dict[str, Any]] = []
        _log_event(event_log, cycle_id=cycle_id, cycle_index=cycle_index, timestamp=cycle_timestamp, phase="cycle_prepare", status=prep.reason)

        retry_item = _dequeue_retry(state=state, cycle_index=cycle_index)
        scout_stage = self._run_scout(snapshot=snapshot, cycle_id=cycle_id, retry_item=retry_item)
        _log_event(
            event_log,
            cycle_id=cycle_id,
            cycle_index=cycle_index,
            timestamp=cycle_timestamp,
            phase="scout",
            status="activated" if scout_stage["activated"] else "observe_only",
            details={"idle_triggered": scout_stage["idle_triggered"]},
        )

        proposal = scout_stage["proposal"]
        boardroom_stage = self.boardroom.execute(
            proposal=proposal,
            snapshot=snapshot,
            cycle_id=cycle_id,
        )
        _log_event(
            event_log,
            cycle_id=cycle_id,
            cycle_index=cycle_index,
            timestamp=cycle_timestamp,
            phase="chief_boardroom",
            status="approved" if bool(_read(boardroom_stage, "decision", "approved")) else "denied",
            details={
                "aggregate_score": _read(boardroom_stage, "decision", "aggregate_score"),
                "chief_override": _read(boardroom_stage, "decision", "chief_override"),
            },
        )

        builder_stage = self._run_builder(
            proposal=proposal,
            boardroom_stage=boardroom_stage,
            cycle_id=cycle_id,
            retry_item=retry_item,
        )
        _log_event(
            event_log,
            cycle_id=cycle_id,
            cycle_index=cycle_index,
            timestamp=cycle_timestamp,
            phase="builder",
            status="prepared_request",
            details={"action_type": builder_stage["action_request"]["action_type"]},
        )

        chief_approved = bool(_read(boardroom_stage, "decision", "approved"))
        action_result = self.action_gate.execute(
            cycle_id=cycle_id,
            action_request=builder_stage["action_request"],
            chief_approved=chief_approved,
            state=state,
        )
        _log_event(
            event_log,
            cycle_id=cycle_id,
            cycle_index=cycle_index,
            timestamp=cycle_timestamp,
            phase="external_gate",
            status=str(action_result.get("status", "")),
        )

        retry_stage = self._route_retry(
            state=state,
            cycle_id=cycle_id,
            cycle_index=cycle_index,
            action_result=action_result,
            proposal=proposal,
            prior_attempt=_as_int(retry_item.get("attempt"), default=1) if isinstance(retry_item, Mapping) else 1,
        )
        _log_event(
            event_log,
            cycle_id=cycle_id,
            cycle_index=cycle_index,
            timestamp=cycle_timestamp,
            phase="retry_router",
            status=retry_stage["route"],
        )

        _update_external_idempotency_state(state=state, action_result=action_result)
        state = self.stability.save_state(state)

        elapsed = time.monotonic() - started
        watchdog_status = "timeout" if elapsed > self.stability.watchdog_timeout_seconds else "ok"
        watchdog_reason = "" if watchdog_status == "ok" else "watchdog_cycle_timeout_exceeded"
        commit_sha = _resolve_commit_sha()
        state_graph_snapshot_hash = canonical_hash(
            {
                "snapshot": dict(snapshot),
                "scout": scout_stage,
                "boardroom": boardroom_stage,
                "builder": builder_stage,
                "external_action": action_result,
                "retry": retry_stage,
                "event_log": event_log,
                "cycle_id": cycle_id,
                "cycle_index": cycle_index,
            }
        )
        run_commit_binding_hash = canonical_hash(
            {
                "run_id": str(phase4_snapshot.run_id),
                "commit_sha": commit_sha,
            }
        )

        runtime_context = {
            "autonomy": {
                "cycle_id": cycle_id,
                "cycle_index": cycle_index,
                "timestamp": cycle_timestamp,
                "heartbeat_seconds": self.heartbeat_seconds,
                "resumed": prep.resumed,
                "idle_triggered": bool(scout_stage["idle_triggered"]),
            },
            "boardroom": boardroom_stage,
            "external_action": action_result,
            "retry": retry_stage,
            "watchdog": {
                "status": watchdog_status,
                "reason": watchdog_reason,
            },
            "audit_binding": {
                "state_graph_snapshot_hash": state_graph_snapshot_hash,
                "run_id": str(phase4_snapshot.run_id),
                "commit_sha": commit_sha,
                "run_commit_binding_hash": run_commit_binding_hash,
                "audit_hardening_state": "COMPLETE_V2",
            },
            "event_log": event_log,
        }

        pipeline_result = self.orchestrator.run_phase4_cycle(
            replay_snapshot=snapshot,
            runtime_context=runtime_context,
        )
        runtime_with_records = dict(runtime_context)
        runtime_with_records["inspection_record"] = dict(pipeline_result.get("inspection_record", {}))
        runtime_with_records["integrity_record"] = dict(pipeline_result.get("integrity_record", {}))
        optimization_summary = self.optimizer.record(runtime_with_records)

        runtime_context["self_optimization"] = {
            "mode": "read_only_output",
            "summary": optimization_summary,
        }
        pipeline_result["runtime"] = runtime_context
        pipeline_result["audit_binding"] = dict(runtime_context.get("audit_binding", {}))

        if watchdog_status == "ok":
            self.stability.mark_cycle_stable(
                cycle_id=cycle_id,
                cycle_index=cycle_index,
                watchdog_status=watchdog_status,
                watchdog_reason=watchdog_reason,
                runtime_trace=runtime_context,
            )
        else:
            self.stability.mark_cycle_failure(cycle_id=cycle_id, reason=watchdog_reason)
        return pipeline_result

    def run_continuous(
        self,
        *,
        max_cycles: int | None = None,
    ) -> List[Dict[str, Any]]:
        completed: List[Dict[str, Any]] = []
        cycle_limit = int(max_cycles) if max_cycles is not None else None

        while True:
            result = self.run_cycle()
            completed.append(result)
            runtime = result.get("runtime", {})
            watchdog = runtime.get("watchdog", {}) if isinstance(runtime, Mapping) else {}
            if str(watchdog.get("status", "")) == "timeout":
                break
            if cycle_limit is not None and len(completed) >= max(0, cycle_limit):
                break
            time.sleep(self.heartbeat_seconds)
        return completed

    def _run_scout(
        self,
        *,
        snapshot: Mapping[str, Any],
        cycle_id: str,
        retry_item: Mapping[str, Any] | None,
    ) -> Dict[str, Any]:
        queue_size = _as_int(snapshot.get("event_queue_size"), default=0)
        running = bool(snapshot.get("running", False))
        idle_triggered = (queue_size <= 0) or (not running)
        activated = idle_triggered or isinstance(retry_item, Mapping)
        source = "retry_queue" if isinstance(retry_item, Mapping) else ("idle_trigger" if idle_triggered else "active_observe")

        if isinstance(retry_item, Mapping) and isinstance(retry_item.get("proposal"), Mapping):
            proposal = dict(retry_item["proposal"])
            proposal["source"] = "retry_queue"
        else:
            proposal = {
                "proposal_id": f"proposal:{canonical_hash({'cycle_id': cycle_id, 'source': source})[:16]}",
                "source": source,
                "target_agent": "forge",
                "action": "READ_ONLY_REPORT" if idle_triggered else "NOOP",
                "idle_triggered": bool(idle_triggered),
                "queue_size": queue_size,
                "running": running,
            }

        return {
            "activated": bool(activated),
            "idle_triggered": bool(idle_triggered),
            "proposal": proposal,
        }

    def _run_builder(
        self,
        *,
        proposal: Mapping[str, Any],
        boardroom_stage: Mapping[str, Any],
        cycle_id: str,
        retry_item: Mapping[str, Any] | None,
    ) -> Dict[str, Any]:
        action_type = str(proposal.get("action", "NOOP")).strip().upper() or "NOOP"
        prior_attempt = _as_int(retry_item.get("attempt"), default=1) if isinstance(retry_item, Mapping) else 1
        action_request = {
            "action_type": action_type,
            "proposal_id": str(proposal.get("proposal_id", "")),
            "target_agent": str(_read(boardroom_stage, "decision", "target_agent") or "forge"),
            "idempotency_key": str(proposal.get("proposal_id", "")) or f"phase4:{cycle_id}:attempt:{prior_attempt}",
            "attempt": prior_attempt,
        }
        return {
            "action_request": action_request,
            "attempt": prior_attempt,
        }

    def _route_retry(
        self,
        *,
        state: Dict[str, Any],
        cycle_id: str,
        cycle_index: int,
        action_result: Mapping[str, Any],
        proposal: Mapping[str, Any],
        prior_attempt: int,
    ) -> Dict[str, Any]:
        status = str(action_result.get("status", ""))
        if status in {"executed", "skipped_duplicate"}:
            return {
                "route": "completed",
                "attempt": prior_attempt,
                "next_retry_cycle": None,
            }

        if prior_attempt >= self.max_retries:
            return {
                "route": "failure_terminal",
                "attempt": prior_attempt,
                "next_retry_cycle": None,
            }

        retry_queue = state.get("retry_queue")
        if not isinstance(retry_queue, list):
            retry_queue = []
        next_retry = {
            "cycle_id": cycle_id,
            "proposal": dict(proposal),
            "attempt": prior_attempt + 1,
            "due_cycle_index": cycle_index + 1,
            "last_status": status,
        }
        retry_queue.append(next_retry)
        retry_queue.sort(
            key=lambda item: (
                _as_int(item.get("due_cycle_index"), default=0),
                str(item.get("cycle_id", "")),
            )
        )
        state["retry_queue"] = retry_queue
        return {
            "route": "retry_scheduled",
            "attempt": prior_attempt,
            "next_retry_cycle": cycle_index + 1,
        }


def _derive_cycle_id(*, phase4_snapshot: Any, cycle_index: int) -> str:
    seed = {
        "run_id": str(phase4_snapshot.run_id),
        "timestamp": str(phase4_snapshot.timestamp),
        "cycle_index": max(1, int(cycle_index)),
    }
    return f"phase4_cycle_{canonical_hash(seed)[:18]}"


def _dequeue_retry(*, state: Dict[str, Any], cycle_index: int) -> Mapping[str, Any] | None:
    retry_queue = state.get("retry_queue")
    if not isinstance(retry_queue, list) or not retry_queue:
        return None
    retry_queue.sort(
        key=lambda item: (
            _as_int(item.get("due_cycle_index"), default=0),
            str(item.get("cycle_id", "")),
        )
    )
    for idx, row in enumerate(retry_queue):
        if not isinstance(row, Mapping):
            continue
        if _as_int(row.get("due_cycle_index"), default=0) <= cycle_index:
            selected = dict(row)
            del retry_queue[idx]
            state["retry_queue"] = retry_queue
            return selected
    state["retry_queue"] = retry_queue
    return None


def _update_external_idempotency_state(*, state: Dict[str, Any], action_result: Mapping[str, Any]) -> None:
    status = str(action_result.get("status", ""))
    if status != "executed":
        return
    key = str(action_result.get("idempotency_key", "")).strip()
    if not key:
        return
    gate_state = state.get("external_gate")
    if not isinstance(gate_state, dict):
        gate_state = {"executed_keys": []}
    executed = gate_state.get("executed_keys")
    if not isinstance(executed, list):
        executed = []
    if key not in executed:
        executed.append(key)
    gate_state["executed_keys"] = executed[-4000:]
    state["external_gate"] = gate_state


def _log_event(
    event_log: List[Dict[str, Any]],
    *,
    cycle_id: str,
    cycle_index: int,
    timestamp: str,
    phase: str,
    status: str,
    details: Mapping[str, Any] | None = None,
) -> None:
    event_log.append(
        {
            "event_index": len(event_log) + 1,
            "cycle_id": str(cycle_id),
            "cycle_index": int(cycle_index),
            "timestamp": str(timestamp),
            "phase": str(phase),
            "status": str(status),
            "details": dict(details) if isinstance(details, Mapping) else {},
        }
    )


def _clamp_heartbeat(value: float) -> float:
    return max(10.0, min(30.0, float(value)))


def _as_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _read(payload: Mapping[str, Any], *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _resolve_commit_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    value = result.stdout.strip()
    return value if value else "unknown"
