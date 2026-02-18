from __future__ import annotations

import asyncio
import json
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional


class GlobalMemory:
    """JSON-based persistent store with isolated agent namespaces."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        root = Path(config.get("memory_root", "appshak_state"))
        self.root_dir = root if root.is_absolute() else Path.cwd() / root
        self.logs_dir = self.root_dir / "logs"
        self.agents_dir = self.root_dir / "agents"

        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.agents_dir.mkdir(parents=True, exist_ok=True)

        self.store_path = self.root_dir / "memory_store.json"
        self.global_log_path = self.logs_dir / "global.jsonl"
        self.error_log_path = self.logs_dir / "errors.jsonl"
        self.external_action_log_path = self.logs_dir / "external_actions.jsonl"

        self._state_lock = asyncio.Lock()
        self._file_lock = asyncio.Lock()
        self._agent_locks: Dict[str, asyncio.Lock] = {}
        self._state: Dict[str, Any] = {
            "updated_at": self._iso_now(),
            "errors": [],
            "agent_namespaces": {},
            "kernel_state": {},
            "external_pipeline": {},
        }

    async def log_error(self, source: str, message: str) -> None:
        record = {
            "timestamp": self._iso_now(),
            "source": source,
            "message": message,
        }
        async with self._state_lock:
            self._state["errors"].append(record)
            self._state["updated_at"] = self._iso_now()

        await self._append_json_line(self.error_log_path, record)
        await self.append_global_log("ERROR", {"source": source, "message": message})

    async def periodic_persist(self) -> None:
        await self._persist_state()

    async def persist_all(self) -> None:
        await self._persist_state()

    async def load_state(self) -> Dict[str, Any]:
        if not self.store_path.exists():
            return dict(self._state)

        async with self._file_lock:
            raw_text = await asyncio.to_thread(self.store_path.read_text, "utf-8")

        try:
            loaded = json.loads(raw_text)
        except json.JSONDecodeError:
            return dict(self._state)

        if not isinstance(loaded, dict):
            return dict(self._state)

        async with self._state_lock:
            self._state = {
                "updated_at": loaded.get("updated_at", self._iso_now()),
                "errors": loaded.get("errors", []),
                "agent_namespaces": loaded.get("agent_namespaces", {}),
                "kernel_state": loaded.get("kernel_state", {}),
                "external_pipeline": loaded.get("external_pipeline", {}),
            }
            return dict(self._state)

    async def save_kernel_state(self, kernel_state: Dict[str, Any]) -> None:
        async with self._state_lock:
            current = self._state.setdefault("kernel_state", {})
            current.update(kernel_state)
            self._state["updated_at"] = self._iso_now()
        await self._persist_state()

    async def get_kernel_state(self) -> Dict[str, Any]:
        async with self._state_lock:
            state = self._state.get("kernel_state", {})
            return dict(state) if isinstance(state, dict) else {}

    async def save_external_pipeline_state(self, pipeline_state: Dict[str, Any]) -> None:
        async with self._state_lock:
            self._state["external_pipeline"] = dict(pipeline_state)
            self._state["updated_at"] = self._iso_now()
        await self._persist_state()

    async def tail_log(
        self,
        log_name: str = "global",
        lines: int = 25,
    ) -> List[str]:
        path = self._log_path(log_name)
        if not path.exists():
            return []
        return await asyncio.to_thread(self._tail_file_lines, path, max(1, lines))

    async def stream_log(
        self,
        log_name: str = "global",
        *,
        start_from_end: bool = True,
        poll_interval: float = 0.5,
        stop_event: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[str]:
        path = self._log_path(log_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()

        with path.open("r", encoding="utf-8") as handle:
            if start_from_end:
                handle.seek(0, 2)
            while True:
                if stop_event is not None and stop_event.is_set():
                    return
                line = handle.readline()
                if line:
                    yield line.rstrip("\n")
                else:
                    await asyncio.sleep(poll_interval)

    async def load_published_events_for_replay(
        self,
        *,
        limit: int = 200,
        include_types: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        allowed_types = {str(item) for item in include_types} if include_types is not None else None
        path = self.global_log_path
        if not path.exists():
            return []

        selected: deque[Dict[str, Any]] = deque(maxlen=max(1, limit))
        with path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("event_type") != "EVENT_PUBLISHED":
                    continue
                payload = rec.get("payload", {})
                if not isinstance(payload, dict):
                    continue
                event_type = str(payload.get("type", ""))
                if allowed_types is not None and event_type not in allowed_types:
                    continue
                selected.append(payload)
        return list(selected)

    async def append_global_log(self, event_type: str, payload: Dict[str, Any]) -> None:
        await self._append_json_line(
            self.global_log_path,
            {"timestamp": self._iso_now(), "event_type": event_type, "payload": payload},
        )

    async def append_agent_event(self, agent_id: str, event: Dict[str, Any]) -> None:
        safe_agent_id = self._sanitize_agent_id(agent_id)
        agent_record = {
            "timestamp": self._iso_now(),
            "event_type": "AGENT_EVENT",
            "payload": event,
        }

        async with self._state_lock:
            namespace = self._state["agent_namespaces"].setdefault(
                safe_agent_id, {"events": [], "updated_at": self._iso_now()}
            )
            namespace["events"].append(agent_record)
            namespace["updated_at"] = self._iso_now()
            self._state["updated_at"] = self._iso_now()

        path = self.agents_dir / f"{safe_agent_id}.jsonl"
        lock = self._agent_locks.setdefault(safe_agent_id, asyncio.Lock())
        await self._append_json_line(path, agent_record, lock=lock)

    async def log_external_action(self, stage: str, payload: Dict[str, Any]) -> None:
        await self._append_json_line(
            self.external_action_log_path,
            {"timestamp": self._iso_now(), "event_type": "EXTERNAL_ACTION", "payload": {"stage": stage, **payload}},
        )

    async def _persist_state(self) -> None:
        async with self._state_lock:
            self._state["updated_at"] = self._iso_now()
            snapshot = json.dumps(self._state, ensure_ascii=True, indent=2)

        async with self._file_lock:
            await asyncio.to_thread(self.store_path.write_text, snapshot, "utf-8")

    async def _append_json_line(
        self,
        path: Path,
        record: Dict[str, Any],
        *,
        lock: asyncio.Lock | None = None,
    ) -> None:
        line = json.dumps(record, ensure_ascii=True) + "\n"
        use_lock = lock or self._file_lock
        async with use_lock:
            await asyncio.to_thread(self._write_line, path, line)

    @staticmethod
    def _write_line(path: Path, line: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file_handle:
            file_handle.write(line)

    def _log_path(self, log_name: str) -> Path:
        normalized = log_name.strip().lower()
        if normalized == "global":
            return self.global_log_path
        if normalized == "errors":
            return self.error_log_path
        if normalized in {"external", "external_actions"}:
            return self.external_action_log_path
        raise ValueError(f"Unknown log name '{log_name}'. Use global/errors/external_actions.")

    @staticmethod
    def _tail_file_lines(path: Path, lines: int) -> List[str]:
        tail: deque[str] = deque(maxlen=lines)
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                tail.append(line.rstrip("\n"))
        return list(tail)

    @staticmethod
    def _sanitize_agent_id(agent_id: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", str(agent_id))
        return cleaned or "agent"

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat()
