from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.types import SubstrateEvent, iso_now


@dataclass(slots=True)
class WorkerState:
    agent_id: str
    process: subprocess.Popen[str]
    consumer_id: str
    worktree: Path
    log_path: Path
    started_monotonic: float


class Supervisor:
    """Supervises per-agent workers with durable liveness and bounded restarts."""

    def __init__(
        self,
        *,
        db_path: str | Path,
        agent_ids: Iterable[str],
        log_path: str | Path = "appshak_state/substrate/supervisor.jsonl",
        human_log_path: str | Path = "appshak_state/substrate/supervisor.log",
        claim_timeout: float = 1.0,
        lease_seconds: float = 15.0,
        include_unrouted: bool = False,
        heartbeat_interval_seconds: float = 5.0,
        heartbeat_timeout_seconds: float = 8.0,
        max_restarts: int = 1000,
        restart_backoff_seconds: float = 1.0,
        restart_backoff_cap_seconds: float = 60.0,
        restart_window_seconds: float = 300.0,
        restart_window_limit: int = 10,
        runtime_log_dir: str | Path = "appshak_state/substrate/workers",
        workspace_roots: Optional[Dict[str, str | Path]] = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.mail_store = SQLiteMailStore(self.db_path, lease_seconds=lease_seconds)
        self.agent_ids: List[str] = [str(agent).strip().lower() for agent in agent_ids if str(agent).strip()]
        if not self.agent_ids:
            raise ValueError("Supervisor requires at least one agent id.")

        self.log_path = Path(log_path)
        self.human_log_path = Path(human_log_path)
        self.claim_timeout = float(claim_timeout)
        self.lease_seconds = float(lease_seconds)
        self.include_unrouted = bool(include_unrouted)
        self.heartbeat_interval_seconds = max(0.2, float(heartbeat_interval_seconds))
        self.heartbeat_timeout_seconds = max(self.heartbeat_interval_seconds * 1.5, float(heartbeat_timeout_seconds))

        self.max_restarts = int(max_restarts)
        self.restart_backoff_seconds = max(0.1, float(restart_backoff_seconds))
        self.restart_backoff_cap_seconds = max(self.restart_backoff_seconds, float(restart_backoff_cap_seconds))
        self.restart_window_seconds = max(5.0, float(restart_window_seconds))
        self.restart_window_limit = max(1, int(restart_window_limit))

        self.runtime_log_dir = Path(runtime_log_dir)
        self.workspace_roots = {
            str(agent).strip().lower(): Path(path).resolve()
            for agent, path in (workspace_roots or {}).items()
        }

        self._workers: Dict[str, WorkerState] = {}
        self._restart_counts: Dict[str, int] = {agent: 0 for agent in self.agent_ids}
        self._restart_history: Dict[str, List[float]] = {agent: [] for agent in self.agent_ids}
        self._scheduled_restarts: Dict[str, float] = {}
        self._disabled_workers: set[str] = set()
        self._recent_control_keys: Dict[str, float] = {}
        self._stop_requested = False
        self._logger = self._build_logger(self.human_log_path)

    def run(self, *, duration_seconds: Optional[float] = None, poll_interval: float = 0.2) -> None:
        self.start()
        deadline = None if duration_seconds is None else (time.monotonic() + max(0.0, duration_seconds))
        next_supervisor_heartbeat = time.monotonic() + self.heartbeat_interval_seconds
        try:
            while not self._stop_requested:
                self._monitor_workers()
                now = time.monotonic()
                if now >= next_supervisor_heartbeat:
                    self.publish_heartbeat()
                    next_supervisor_heartbeat = now + self.heartbeat_interval_seconds
                if deadline is not None and now >= deadline:
                    break
                time.sleep(max(0.05, poll_interval))
        finally:
            self.stop()

    def start(self) -> None:
        self._stop_requested = False
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.runtime_log_dir.mkdir(parents=True, exist_ok=True)
        self._logger.info("SUPERVISOR_START agents=%s db=%s", self.agent_ids, self.db_path)
        self.publish_control_event(
            "SUPERVISOR_START",
            payload={"agents": self.agent_ids, "db_path": str(self.db_path)},
            dedupe_key="supervisor_start",
            dedupe_ttl_seconds=1.0,
        )
        for agent_id in self.agent_ids:
            if agent_id in self._disabled_workers:
                continue
            if agent_id not in self._workers:
                self._spawn_worker(agent_id, is_restart=False)

    def stop(self) -> None:
        if self._stop_requested:
            self._close_logger()
            return
        self._stop_requested = True
        for agent_id, worker in list(self._workers.items()):
            proc = worker.process
            exit_code = proc.poll()
            if exit_code is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5.0)
            self._workers.pop(agent_id, None)
            self._record_worker_event("WORKER_EXITED", agent_id, {"exit_code": proc.returncode, "reason": "stop"})
        self.publish_control_event(
            "SUPERVISOR_STOP",
            payload={},
            dedupe_key="supervisor_stop",
            dedupe_ttl_seconds=1.0,
        )
        self._logger.info("SUPERVISOR_STOP")
        self._close_logger()

    def publish_event(self, event: SubstrateEvent | Dict[str, object]) -> int:
        return self.mail_store.append_event(event)

    def publish_heartbeat(self) -> None:
        cycle = int(time.time())
        for agent_id in self.agent_ids:
            if agent_id in self._disabled_workers:
                continue
            correlation_id = f"supervisor_heartbeat:{agent_id}:{cycle}"
            self.publish_control_event(
                "SUPERVISOR_HEARTBEAT",
                agent_id=agent_id,
                correlation_id=correlation_id,
                dedupe_key=correlation_id,
                dedupe_ttl_seconds=self.heartbeat_interval_seconds * 0.8,
                payload={
                    "agent_id": agent_id,
                    "heartbeat_at": iso_now(),
                    "prime_directive_justification": (
                        "Supervisor heartbeat preserves worker liveness and durable orchestration."
                    ),
                },
            )

    def publish_control_event(
        self,
        event_type: str,
        *,
        agent_id: Optional[str] = None,
        payload: Optional[Dict[str, object]] = None,
        correlation_id: Optional[str] = None,
        dedupe_key: Optional[str] = None,
        dedupe_ttl_seconds: float = 1.0,
    ) -> Optional[int]:
        now_mono = time.monotonic()
        key = dedupe_key or f"{event_type}:{agent_id or 'all'}"
        previous = self._recent_control_keys.get(key)
        if previous is not None and (now_mono - previous) < max(0.0, dedupe_ttl_seconds):
            return None
        self._recent_control_keys[key] = now_mono

        corr = correlation_id or f"{event_type}:{agent_id or 'all'}:{int(time.time())}"
        idempotency_key = f"control:{corr}"
        reserved = self.mail_store.reserve_idempotency_key(
            idempotency_key,
            agent_id="supervisor",
            action_type="CONTROL_EVENT",
        )
        if not reserved:
            return None

        event_payload = dict(payload or {})
        event_payload.setdefault("idempotency_key", idempotency_key)
        event_payload.setdefault("correlation_id", corr)
        event_payload.setdefault(
            "prime_directive_justification",
            "Supervisor control events maintain resilient, safe swarm operation.",
        )
        event_id = self.mail_store.append_event(
            SubstrateEvent(
                type=event_type,
                origin_id="supervisor",
                target_agent=agent_id,
                correlation_id=corr,
                payload=event_payload,
            )
        )
        self.mail_store.set_idempotency_result(idempotency_key, {"event_id": event_id, "event_type": event_type})
        return event_id

    def kill_worker(self, agent_id: str) -> bool:
        normalized = str(agent_id).strip().lower()
        worker = self._workers.get(normalized)
        if worker is None:
            return False
        proc = worker.process
        if proc.poll() is None:
            proc.kill()
        self._logger.warning("WORKER_KILLED agent=%s pid=%s", normalized, proc.pid)
        return True

    def worker_pids(self) -> Dict[str, int]:
        return {
            agent: state.process.pid
            for agent, state in self._workers.items()
            if state.process.poll() is None
        }

    def restart_count(self, agent_id: str) -> int:
        return int(self._restart_counts.get(str(agent_id).strip().lower(), 0))

    def is_worker_disabled(self, agent_id: str) -> bool:
        return str(agent_id).strip().lower() in self._disabled_workers

    def _monitor_workers(self) -> None:
        now = time.monotonic()
        for agent_id, worker in list(self._workers.items()):
            proc = worker.process
            exit_code = proc.poll()
            if exit_code is not None:
                self._workers.pop(agent_id, None)
                self._record_worker_event("WORKER_EXITED", agent_id, {"exit_code": exit_code, "reason": "process_exit"})
                self._schedule_restart_or_disable(agent_id, reason="process_exit", details={"exit_code": exit_code})
                continue

            if self._heartbeat_missing(worker, now):
                self._record_worker_event(
                    "WORKER_HEARTBEAT_MISSED",
                    agent_id,
                    {"pid": proc.pid, "consumer_id": worker.consumer_id},
                )
                self._logger.warning("WORKER_HEARTBEAT_MISSED agent=%s pid=%s", agent_id, proc.pid)
                proc.kill()
                try:
                    proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                self._workers.pop(agent_id, None)
                self._record_worker_event(
                    "WORKER_EXITED",
                    agent_id,
                    {"exit_code": proc.returncode, "reason": "heartbeat_missed"},
                )
                self._schedule_restart_or_disable(agent_id, reason="heartbeat_missed", details={"exit_code": proc.returncode})

        for agent_id, restart_at in list(self._scheduled_restarts.items()):
            if self._stop_requested or agent_id in self._disabled_workers:
                self._scheduled_restarts.pop(agent_id, None)
                continue
            if now < restart_at:
                continue
            self._spawn_worker(agent_id, is_restart=True)
            self._scheduled_restarts.pop(agent_id, None)

    def _heartbeat_missing(self, worker: WorkerState, now_monotonic: float) -> bool:
        hb = self.mail_store.get_worker_heartbeat(worker.agent_id)
        if hb is None:
            return (now_monotonic - worker.started_monotonic) > self.heartbeat_timeout_seconds
        hb_ts = hb.get("ts")
        if not isinstance(hb_ts, str):
            return True
        try:
            parsed = datetime.fromisoformat(hb_ts)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        except Exception:
            return True
        age = (datetime.now(timezone.utc) - parsed).total_seconds()
        return age > self.heartbeat_timeout_seconds

    def _schedule_restart_or_disable(self, agent_id: str, *, reason: str, details: Dict[str, object]) -> None:
        if self._stop_requested:
            return
        normalized = str(agent_id).strip().lower()
        now = time.monotonic()

        restart_count = self._restart_counts.get(normalized, 0) + 1
        self._restart_counts[normalized] = restart_count
        history = [stamp for stamp in self._restart_history.get(normalized, []) if (now - stamp) <= self.restart_window_seconds]
        history.append(now)
        self._restart_history[normalized] = history

        exceeded_window = len(history) > self.restart_window_limit
        exceeded_total = restart_count > self.max_restarts
        if exceeded_window or exceeded_total:
            self._disabled_workers.add(normalized)
            self._scheduled_restarts.pop(normalized, None)
            self._record_worker_event(
                "WORKER_DISABLED",
                normalized,
                {
                    "reason": reason,
                    "restart_count": restart_count,
                    "restart_window_count": len(history),
                    "restart_window_seconds": self.restart_window_seconds,
                    **details,
                },
            )
            self.publish_control_event(
                "SUPERVISOR_ALERT",
                agent_id="command",
                correlation_id=f"alert:{normalized}:{int(time.time())}",
                dedupe_key=f"alert:{normalized}",
                dedupe_ttl_seconds=2.0,
                payload={
                    "agent_id": normalized,
                    "alert": "worker_disabled",
                    "reason": reason,
                    "restart_count": restart_count,
                    "restart_window_count": len(history),
                    "details": details,
                },
            )
            self._logger.error(
                "WORKER_DISABLED agent=%s reason=%s restart_count=%s window_count=%s",
                normalized,
                reason,
                restart_count,
                len(history),
            )
            return

        delay = min(
            self.restart_backoff_cap_seconds,
            self.restart_backoff_seconds * (2 ** max(0, restart_count - 1)),
        )
        restart_at = now + delay
        self._scheduled_restarts[normalized] = restart_at
        self._logger.warning(
            "WORKER_RESTART_SCHEDULED agent=%s reason=%s restart_count=%s delay=%.2fs",
            normalized,
            reason,
            restart_count,
            delay,
        )
        self._record_worker_event(
            "WORKER_RESTART_SCHEDULED",
            normalized,
            {
                "reason": reason,
                "restart_count": restart_count,
                "restart_in_seconds": delay,
                **details,
            },
        )

    def _spawn_worker(self, agent_id: str, *, is_restart: bool) -> None:
        normalized = str(agent_id).strip().lower()
        if normalized in self._disabled_workers:
            return

        worktree = self.workspace_roots.get(normalized, Path.cwd().resolve())
        if not worktree.exists():
            raise RuntimeError(f"Missing worktree path for agent '{normalized}': {worktree}")

        consumer_id = f"worker:{normalized}:{int(time.time() * 1000)}"
        worker_log_path = self.runtime_log_dir / f"{normalized}.log"
        cmd = [
            sys.executable,
            "-m",
            "appshak_substrate.worker_process",
            "--agent-id",
            normalized,
            "--db-path",
            str(self.db_path),
            "--worktree",
            str(worktree),
            "--consumer-id",
            consumer_id,
            "--log-path",
            str(worker_log_path),
            "--claim-timeout",
            str(self.claim_timeout),
            "--lease-seconds",
            str(self.lease_seconds),
            "--heartbeat-interval-seconds",
            str(min(self.heartbeat_interval_seconds, self.heartbeat_timeout_seconds / 2.0)),
        ]
        if self.include_unrouted:
            cmd.append("--include-unrouted")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        worker = WorkerState(
            agent_id=normalized,
            process=process,
            consumer_id=consumer_id,
            worktree=worktree,
            log_path=worker_log_path,
            started_monotonic=time.monotonic(),
        )
        self._workers[normalized] = worker
        event_type = "WORKER_RESTARTED" if is_restart else "WORKER_STARTED"
        self._record_worker_event(
            event_type,
            normalized,
            {
                "pid": process.pid,
                "consumer_id": consumer_id,
                "worktree": str(worktree),
                "log_path": str(worker_log_path),
                "cmd": cmd,
            },
        )
        self._logger.info("%s agent=%s pid=%s", event_type, normalized, process.pid)

    def _record_worker_event(self, event_type: str, agent_id: str, details: Dict[str, object]) -> None:
        correlation_id = f"{event_type}:{agent_id}:{int(time.time() * 1000)}"
        self.publish_control_event(
            event_type,
            agent_id="command",
            correlation_id=correlation_id,
            dedupe_key=correlation_id,
            dedupe_ttl_seconds=0.0,
            payload={"agent_id": agent_id, **details},
        )
        self._log_json(event_type, {"agent_id": agent_id, **details})

    def _log_json(self, event_type: str, payload: Dict[str, object]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": iso_now(),
            "event_type": event_type,
            "payload": payload,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")

    @staticmethod
    def _build_logger(path: Path) -> logging.Logger:
        logger = logging.getLogger(f"appshak.substrate.supervisor.{path.stem}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.handlers = []
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        return logger

    def _close_logger(self) -> None:
        for handler in list(self._logger.handlers):
            try:
                handler.flush()
                handler.close()
            finally:
                self._logger.removeHandler(handler)
