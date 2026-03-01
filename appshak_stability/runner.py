from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping

from appshak_governance.ledger import GovernanceAuditLedger
from appshak_integrity.store import IntegrityReportStore
from appshak_inspection.store import InspectionIndexStore

from .store import StabilityRunStore
from .utils import load_json, timestamp_token, utc_now_iso


class StabilityRunner:
    def __init__(
        self,
        *,
        duration_hours: float,
        poll_interval_seconds: float = 60.0,
        checkpoint_every_cycles: int = 5,
        projection_view_path: Path | str = "appshak_state/projection/view.json",
        governance_ledger_path: Path | str = "appshak_state/governance/ledger.jsonl",
        integrity_root: Path | str = "appshak_state/integrity",
        inspection_root: Path | str = "appshak_state/inspection",
        stability_root: Path | str = "appshak_state/stability",
    ) -> None:
        self.duration_hours = max(0.01, float(duration_hours))
        self.poll_interval_seconds = max(1.0, float(poll_interval_seconds))
        self.checkpoint_every_cycles = max(1, int(checkpoint_every_cycles))
        self.projection_view_path = Path(projection_view_path)
        self.governance_ledger_path = Path(governance_ledger_path)
        self.integrity_store = IntegrityReportStore(integrity_root)
        self.inspection_store = InspectionIndexStore(inspection_root)
        self.run_store = StabilityRunStore(stability_root)
        self.governance_ledger = GovernanceAuditLedger(self.governance_ledger_path)

    def run(self) -> Dict[str, Any]:
        started_at = utc_now_iso()
        run_id = f"run_{timestamp_token(started_at)}"
        run_dir = self.run_store.init_run(
            run_id=run_id,
            meta={
                "run_id": run_id,
                "status": "running",
                "duration_hours": self.duration_hours,
                "poll_interval_seconds": self.poll_interval_seconds,
                "checkpoint_every_cycles": self.checkpoint_every_cycles,
                "started_at": started_at,
                "updated_at": started_at,
                "completed_at": None,
                "incident": None,
            },
        )

        total_cycles = max(1, int(math.ceil((self.duration_hours * 3600.0) / self.poll_interval_seconds)))
        incident: Dict[str, Any] | None = None
        start_monotonic = time.monotonic()

        for cycle in range(total_cycles):
            cycle_started_at = utc_now_iso()
            snapshot = load_json(self.projection_view_path)
            inspection = self.inspection_store.load_latest()
            integrity = self.integrity_store.load_latest()
            replay_checkpoint = self._governance_hash_checkpoint(snapshot=snapshot)
            checkpoint_payload = {
                "run_id": run_id,
                "checkpoint_id": cycle + 1,
                "cycle": cycle,
                "timestamp": cycle_started_at,
                "projection_timestamp": _as_string(snapshot.get("timestamp")),
                "inspection_timestamp": _as_string(inspection.get("generated_at")),
                "integrity_timestamp": _as_string(integrity.get("generated_at")),
                "governance_replay_hash_checkpoint": replay_checkpoint.get("replay_hash"),
                "ledger_reconstruction_hash_checkpoint": replay_checkpoint.get("reconstruction_hash"),
                "integrity_report_hash": integrity.get("report_hash"),
                "watchdog": {"status": "ok", "reason": None},
            }

            incident = self._detect_incident(snapshot=snapshot, cycle=cycle)
            if incident is not None:
                checkpoint_payload["watchdog"] = {"status": "incident", "reason": incident.get("reason")}
                self.run_store.checkpoint(run_dir=run_dir, checkpoint_id=cycle + 1, payload=checkpoint_payload)
                break

            should_checkpoint = ((cycle + 1) % self.checkpoint_every_cycles == 0) or (cycle == total_cycles - 1)
            if should_checkpoint:
                self.run_store.checkpoint(run_dir=run_dir, checkpoint_id=cycle + 1, payload=checkpoint_payload)

            target_time = start_monotonic + (cycle + 1) * self.poll_interval_seconds
            sleep_seconds = max(0.0, target_time - time.monotonic())
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        completed_at = utc_now_iso()
        final_status = "halted" if incident is not None else "completed"
        self.run_store.update_meta(
            run_dir=run_dir,
            payload={
                "run_id": run_id,
                "status": final_status,
                "duration_hours": self.duration_hours,
                "poll_interval_seconds": self.poll_interval_seconds,
                "checkpoint_every_cycles": self.checkpoint_every_cycles,
                "started_at": started_at,
                "updated_at": completed_at,
                "completed_at": completed_at,
                "incident": incident,
            },
        )
        return self.run_store.load_run(run_id)

    def _governance_hash_checkpoint(self, *, snapshot: Mapping[str, Any]) -> Dict[str, Any]:
        chain_valid = self.governance_ledger.validate_hash_chain()
        reconstructed = self.governance_ledger.reconstruct_registry(fallback_registry={"agents": {}, "history": {}})
        replay_hash = ""
        if isinstance(reconstructed, Mapping):
            replay_hash = str(snapshot.get("governance_replay_hash", "")) or str(
                reconstructed.get("registry_hash", "")
            )
        reconstruction_hash = ""
        if isinstance(reconstructed, Mapping):
            from appshak_governance.utils import canonical_hash

            reconstruction_hash = canonical_hash(reconstructed)
        return {
            "chain_valid": chain_valid,
            "replay_hash": replay_hash,
            "reconstruction_hash": reconstruction_hash,
        }

    @staticmethod
    def _detect_incident(*, snapshot: Mapping[str, Any], cycle: int) -> Dict[str, Any] | None:
        workers = snapshot.get("workers")
        if isinstance(workers, Mapping):
            for worker_id, worker_state in workers.items():
                if not isinstance(worker_state, Mapping):
                    continue
                missed = int(worker_state.get("missed_heartbeat_count", 0))
                state = str(worker_state.get("state", "")).strip().upper()
                if missed >= 3 or state == "OFFLINE":
                    return {
                        "type": "watchdog_worker_offline",
                        "reason": f"worker={worker_id} state={state} missed_heartbeat_count={missed}",
                        "cycle": cycle,
                    }
        event_queue_size = int(snapshot.get("event_queue_size", 0))
        running = bool(snapshot.get("running", False))
        if cycle >= 2 and (not running) and event_queue_size > 0:
            return {
                "type": "watchdog_queue_stall",
                "reason": "running=false while queue remains non-zero",
                "cycle": cycle,
            }
        return None


def _as_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None
