from __future__ import annotations

import sys
import subprocess
import sqlite3
import threading
from contextlib import closing
import tempfile
import time
import unittest
from pathlib import Path

from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.policy import ToolPolicy
from appshak_substrate.tool_gateway import ToolGateway
from appshak_substrate.types import SubstrateEvent, iso_now


class TestRecoverableExecution(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="appshak_wp2_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "worker"
        self.workspace.mkdir()
        self.db = self.root / "mail.db"
        self.store = SQLiteMailStore(self.db, lease_seconds=0.3, poll_interval=0.01)
        self.gateway = ToolGateway(mail_store=self.store, policy=ToolPolicy(chief_agent_id="command",
            allowed_command_prefixes=[(sys.executable,)]), workspace_roots={"command": self.workspace},
            command_timeout_seconds=3)

    def request(self, name: str, *, action: str = "WRITE_FILE", payload: dict | None = None,
                source_event_id: int | None = None) -> dict:
        return {
            "agent_id": "command", "authorized_by": "command", "action_type": action,
            "working_dir": str(self.workspace), "authority_id": f"authority:{name}",
            "source_request_id": f"request:{name}",
            "workspace_id": ToolGateway.workspace_identity("command", self.workspace),
            "requested_operation": action, "created_at": iso_now(),
            "source_event_id": source_event_id, "reply_to": "command",
            "payload": payload or {"path": f"{name}.txt", "content": name,
                                   "idempotency_key": f"key:{name}"},
        }

    def reserve(self, request: dict) -> dict:
        normalized = self.gateway.policy.validate(self.gateway._coerce_request(request),
                                                   worktree_root=self.workspace).normalized_payload
        normalized.update({key: request[key] for key in
                           ("authority_id", "source_request_id", "workspace_id",
                            "requested_operation", "created_at")})
        normalized["worker_id"] = request["agent_id"]
        contract = {"working_dir": request["working_dir"], "payload": normalized,
                    "authorized_by": request["authorized_by"], "correlation_id": None,
                    "reply_to": request["reply_to"]}
        return self.store.reserve_attempt(
            source_request_id=request["source_request_id"], source_event_id=request["source_event_id"],
            idempotency_key=request["payload"]["idempotency_key"], authority_id=request["authority_id"],
            agent_id=request["agent_id"], workspace_id=request["workspace_id"],
            requested_operation=request["requested_operation"], created_at=request["created_at"],
            request=contract)

    def test_active_duplicate_and_durable_success_redelivery(self) -> None:
        req = self.request("once")
        attempt = self.reserve(req)
        generation = self.store.begin_attempt(attempt["attempt_id"], "worker:a", 1)
        self.assertEqual(generation, 1)
        blocked = self.gateway.execute(req)
        self.assertFalse(blocked.allowed)
        self.assertFalse((self.workspace / "once.txt").exists())
        self.assertEqual(len(self.store.list_attempts()), 1)
        self.store.reconcile_attempts()
        self.assertEqual(self.store.get_attempt(attempt["attempt_id"])["state"], "RUNNING")
        self.assertTrue(self.store.renew_attempt_lease(attempt["attempt_id"], "worker:a", 1, 1))

        other = self.request("completed")
        first = self.gateway.execute(other)
        self.assertTrue(first.allowed)
        self.assertEqual(self.store.get_attempt(first.attempt_id)["state"], "SUCCEEDED")
        (self.workspace / "completed.txt").write_text("changed", encoding="utf-8")
        replay = self.gateway.execute(other)
        self.assertTrue(replay.allowed)
        self.assertEqual(replay.attempt_id, first.attempt_id)
        self.assertEqual((self.workspace / "completed.txt").read_text(encoding="utf-8"), "changed")
        bypass = dict(other)
        bypass["payload"] = {**other["payload"], "allow_duplicate": True}
        self.assertFalse(self.gateway.execute(bypass).allowed)
        self.assertEqual((self.workspace / "completed.txt").read_text(encoding="utf-8"), "changed")

    def test_concurrent_duplicate_runs_effect_once(self) -> None:
        marker = self.workspace / "effect-count.txt"
        script = self.workspace / "one_effect.py"
        script.write_text(
            f"from pathlib import Path\nimport time\n"
            f"with Path({str(marker)!r}).open('a') as output: output.write('effect\\n')\n"
            "time.sleep(0.7)\n", encoding="utf-8")
        req = self.request("concurrent", action="RUN_CMD", payload={
            "argv": [sys.executable, str(script)], "idempotency_key": "key:concurrent"})
        results = []
        first = threading.Thread(target=lambda: results.append(self.gateway.execute(req)))
        first.start()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not marker.exists():
            time.sleep(0.02)
        self.assertTrue(marker.exists())
        duplicate = self.gateway.execute(req)
        first.join(timeout=3)
        self.assertFalse(first.is_alive())
        self.assertFalse(duplicate.allowed)
        self.assertTrue(results[0].allowed)
        self.assertEqual(marker.read_text(encoding="utf-8").splitlines(), ["effect"])
        self.assertEqual(len(self.store.list_attempts()), 1)

    def test_reservation_crash_and_unknown_effect_window(self) -> None:
        reserved_req = self.request("reserved")
        reserved = self.reserve(reserved_req)
        restarted = SQLiteMailStore(self.db, lease_seconds=0.3)
        self.assertEqual(restarted.reconcile_attempts()["fenced_unknown"], 0)
        self.assertEqual(restarted.get_attempt(reserved["attempt_id"])["state"], "RESERVED")
        self.assertTrue(self.gateway.execute(reserved_req).allowed)

        unsafe_req = self.request("unsafe")
        unsafe = self.reserve(unsafe_req)
        fence = self.store.begin_attempt(unsafe["attempt_id"], "worker:a", 0.15)
        (self.workspace / "unsafe.txt").write_text("effect occurred", encoding="utf-8")
        time.sleep(0.2)
        self.assertEqual(restarted.reconcile_attempts()["fenced_unknown"], 1)
        self.assertEqual(restarted.get_attempt(unsafe["attempt_id"])["state"], "NEEDS_RECONCILIATION")
        self.assertIsNone(self.store.record_attempt_outcome(unsafe["attempt_id"], "worker:a", fence,
                                                             "SUCCEEDED", {"allowed": True}))
        self.assertFalse(self.gateway.execute(unsafe_req).allowed)
        self.assertEqual((self.workspace / "unsafe.txt").read_text(encoding="utf-8"), "effect occurred")
        self.assertEqual(restarted.get_attempt(unsafe["attempt_id"])["authority_id"], unsafe_req["authority_id"])

    def test_outcome_publication_and_ack_recovery(self) -> None:
        event_id = self.store.append_event(SubstrateEvent(type="TOOL_REQUEST", origin_id="command",
                                                          target_agent="command", payload={}))
        self.assertEqual(self.store.claim_next_event("test-direct-a", timeout=0.1,
            target_agent="command", include_unrouted=False).event_id, event_id)
        req = self.request("published", source_event_id=event_id)
        first = self.gateway.execute(req, owner_id="test-direct-a")
        self.assertTrue(first.allowed)
        restarted = SQLiteMailStore(self.db)
        self.assertIsNone(restarted.get_attempt(first.attempt_id)["published_event_id"])
        (self.workspace / "published.txt").write_text("preserved", encoding="utf-8")
        self._run_recovery_worker(event_id, "recover-outcome")
        publication = restarted.get_attempt(first.attempt_id)["published_event_id"]
        self.assertIsNotNone(publication)
        self.assertEqual(restarted.publish_attempt_result(first.attempt_id), publication)
        self.assertEqual(len([e for e in restarted.list_events() if e.type == "TOOL_RESULT"]), 1)
        self.assertEqual((self.workspace / "published.txt").read_text(encoding="utf-8"), "preserved")
        self.assertEqual(restarted.get_event(event_id).status, "DONE")
        self.assertEqual(self.gateway.execute(req).attempt_id, first.attempt_id)
        self.assertEqual(len(restarted.list_attempts()), 1)

        second_id = self.store.append_event(SubstrateEvent(type="TOOL_REQUEST", origin_id="command",
                                                           target_agent="command", payload={}))
        while True:
            claimed = self.store.claim_next_event("test-direct-b", timeout=0.1,
                target_agent="command", include_unrouted=False)
            self.assertIsNotNone(claimed)
            if claimed.event_id == second_id:
                break
            self.store.ack_event(claimed.event_id, consumer_id="test-direct-b")
        second_req = self.request("ack", source_event_id=second_id)
        second = self.gateway.execute(second_req, owner_id="test-direct-b")
        second_publication = self.store.publish_attempt_result(second.attempt_id)
        self.assertIsNotNone(second_publication)
        (self.workspace / "ack.txt").write_text("preserved", encoding="utf-8")
        self._run_recovery_worker(second_id, "recover-ack")
        self.assertEqual(self.store.get_event(second_id).status, "DONE")
        self.assertEqual(self.store.get_attempt(second.attempt_id)["published_event_id"], second_publication)
        self.assertEqual((self.workspace / "ack.txt").read_text(encoding="utf-8"), "preserved")

    def _run_recovery_worker(self, event_id: int, consumer_id: str) -> None:
        worker = subprocess.Popen(
            [sys.executable, "-m", "appshak_substrate.worker_process",
             "--db-path", str(self.db), "--agent-id", "command",
             "--worktree", str(self.workspace), "--consumer-id", consumer_id,
             "--log-path", str(self.root / f"{consumer_id}.log"),
             "--lease-seconds", "0.3", "--heartbeat-interval-seconds", "0.05"],
            cwd=str(Path(__file__).resolve().parents[1]), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and self.store.get_event(event_id).status != "DONE":
                time.sleep(0.05)
            self.assertEqual(self.store.get_event(event_id).status, "DONE",
                             self.store.get_event(event_id).error)
        finally:
            worker.terminate()
            try:
                worker.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.communicate(timeout=3)

    def test_stale_fence_and_long_running_renewal(self) -> None:
        req = self.request("fence")
        attempt = self.reserve(req)
        fence = self.store.begin_attempt(attempt["attempt_id"], "worker:a", 0.1)
        time.sleep(0.13)
        self.store.reconcile_attempts()
        self.assertFalse(self.store.renew_attempt_lease(attempt["attempt_id"], "worker:a", fence, 1))
        self.assertIsNone(self.store.record_attempt_outcome(attempt["attempt_id"], "worker:a", fence,
                                                             "SUCCEEDED", {"allowed": True}))
        script = self.workspace / "sleep.py"
        script.write_text("import time\ntime.sleep(0.9)\nprint('done')\n", encoding="utf-8")
        command = self.request("slow", action="RUN_CMD", payload={
            "argv": [sys.executable, str(script)], "idempotency_key": "key:slow"})
        result = self.gateway.execute(command)
        self.assertTrue(result.allowed)
        self.assertEqual(result.return_code, 0)
        self.assertEqual(self.store.get_attempt(result.attempt_id)["state"], "SUCCEEDED")

    def test_stale_source_event_lease_cannot_commit_success(self) -> None:
        event_id = self.store.append_event(SubstrateEvent(type="TOOL_REQUEST", origin_id="command",
                                                          target_agent="command", payload={}))
        claimed = self.store.claim_next_event("owner:a", timeout=0.1, target_agent="command",
                                              include_unrouted=False, lease_seconds=0.15)
        self.assertEqual(claimed.event_id, event_id)
        req = self.request("source-fence", source_event_id=event_id)
        attempt = self.reserve(req)
        generation = self.store.begin_attempt(attempt["attempt_id"], "owner:a", 1)
        self.assertEqual(generation, 1)
        time.sleep(0.2)
        reclaimed = self.store.claim_next_event("owner:b", timeout=0.1, target_agent="command",
                                                include_unrouted=False, lease_seconds=1)
        self.assertEqual(reclaimed.event_id, event_id)
        self.assertIsNone(self.store.record_attempt_outcome(attempt["attempt_id"], "owner:a",
                          generation, "SUCCEEDED", {"allowed": True}))
        self.assertIsNone(self.store.get_attempt(attempt["attempt_id"])["outcome"])

    def test_timeout_kills_child_tree(self) -> None:
        child = self.workspace / "child.py"
        marker = self.workspace / "child-survived.txt"
        child.write_text(f"import time\nfrom pathlib import Path\ntime.sleep(2)\nPath({str(marker)!r}).write_text('orphan')\n",
                         encoding="utf-8")
        parent = self.workspace / "parent.py"
        parent.write_text(f"import subprocess,sys,time\nsubprocess.Popen([sys.executable,{str(child)!r}])\ntime.sleep(10)\n",
                          encoding="utf-8")
        self.gateway.command_timeout_seconds = 1.0
        req = self.request("timeout", action="RUN_CMD", payload={
            "argv": [sys.executable, str(parent)], "idempotency_key": "key:timeout"})
        result = self.gateway.execute(req)
        self.assertFalse(result.allowed)
        self.assertEqual(self.store.get_attempt(result.attempt_id)["state"], "TIMED_OUT")
        time.sleep(2.2)
        self.assertFalse(marker.exists())

    def test_nonzero_exit_is_durable_failure(self) -> None:
        script = self.workspace / "nonzero.py"
        script.write_text("import sys\nsys.exit(7)\n", encoding="utf-8")
        req = self.request("nonzero", action="RUN_CMD", payload={
            "argv": [sys.executable, str(script)], "idempotency_key": "key:nonzero"})
        result = self.gateway.execute(req)
        self.assertFalse(result.allowed)
        self.assertEqual(result.return_code, 7)
        self.assertEqual(self.store.get_attempt(result.attempt_id)["state"], "FAILED")
        self.assertEqual(self.gateway.execute(req).return_code, 7)

    def test_existing_database_migration_preserves_rows(self) -> None:
        legacy_db = self.root / "legacy.db"
        schema = (Path(__file__).resolve().parents[1] / "appshak_substrate" / "schema.sql").read_text(
            encoding="utf-8").split("CREATE TABLE IF NOT EXISTS execution_attempts")[0]
        with closing(sqlite3.connect(legacy_db)) as conn:
            conn.executescript(schema)
            conn.execute("INSERT INTO events (ts,type,origin_id,payload_json,status) VALUES (?,?,?,?,?)",
                         (iso_now(), "TEST", "test", "{}", "PENDING"))
            conn.execute("INSERT INTO idempotency_keys (idempotency_key,created_ts,agent_id,action_type) VALUES (?,?,?,?)",
                         ("legacy", iso_now(), "command", "READ_FILE"))
            conn.commit()
        reopened = SQLiteMailStore(legacy_db)
        event_id = 1
        self.assertIsNotNone(reopened.get_event(event_id))
        self.assertIsNotNone(reopened.get_idempotency_record("legacy"))
        self.assertEqual(reopened.list_attempts(), [])
        migrated = SQLiteMailStore(legacy_db)
        self.assertIsNotNone(migrated.get_event(event_id))
        with self.assertRaisesRegex(ValueError, "Legacy idempotency"):
            migrated.reserve_attempt(source_request_id="legacy-request", source_event_id=None,
                idempotency_key="legacy", authority_id="authority:legacy", agent_id="command",
                workspace_id="workspace", requested_operation="READ_FILE", created_at=iso_now(),
                request={"working_dir": str(self.workspace), "payload": {}})

    def test_worker_publishes_and_acks_durable_attempt(self) -> None:
        req = self.request("worker")
        event_id = self.store.append_event(SubstrateEvent(
            type="TOOL_REQUEST", origin_id="command", target_agent="command",
            payload={"request": req, "reply_to": "command"}))
        cmd = [sys.executable, "-m", "appshak_substrate.worker_process",
               "--db-path", str(self.db), "--agent-id", "command",
               "--worktree", str(self.workspace), "--consumer-id", "test-worker",
               "--log-path", str(self.root / "worker.log"),
               "--lease-seconds", "0.3", "--heartbeat-interval-seconds", "0.05"]
        worker = subprocess.Popen(cmd, cwd=str(Path(__file__).resolve().parents[1]),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline:
                if self.store.get_event(event_id).status == "DONE":
                    break
                if worker.poll() is not None:
                    raise AssertionError(f"Worker exited early: {worker.communicate()[1]}")
                time.sleep(0.05)
            source = self.store.get_event(event_id)
            self.assertEqual(source.status, "DONE", f"{source.error}; attempts={self.store.list_attempts()}")
            attempts = self.store.list_attempts()
            self.assertEqual(len(attempts), 1)
            self.assertEqual(attempts[0]["state"], "SUCCEEDED")
            self.assertIsNotNone(attempts[0]["published_event_id"])
            self.assertIsNotNone(attempts[0]["acknowledged_at"])
            self.assertEqual(attempts[0]["authority_id"], req["authority_id"])
            self.assertEqual((self.workspace / "worker.txt").read_text(encoding="utf-8"), "worker")
        finally:
            worker.terminate()
            try:
                worker.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.communicate(timeout=3)

    def test_worker_renews_event_and_heartbeat_during_tool(self) -> None:
        (self.workspace / "test_slow.py").write_text(
            "import time\nimport unittest\nclass Slow(unittest.TestCase):\n"
            "    def test_wait(self):\n        time.sleep(2.2)\n", encoding="utf-8")
        req = self.request("worker-slow", action="RUN_CMD", payload={
            "argv": ["python", "-m", "unittest", "test_slow"],
            "idempotency_key": "key:worker-slow"})
        event_id = self.store.append_event(SubstrateEvent(
            type="TOOL_REQUEST", origin_id="command", target_agent="command",
            payload={"request": req, "reply_to": "command"}))
        worker = subprocess.Popen(
            [sys.executable, "-m", "appshak_substrate.worker_process",
             "--db-path", str(self.db), "--agent-id", "command",
             "--worktree", str(self.workspace), "--consumer-id", "test-slow-worker",
             "--log-path", str(self.root / "slow.log"),
             "--lease-seconds", "0.8", "--heartbeat-interval-seconds", "0.1"],
            cwd=str(Path(__file__).resolve().parents[1]), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline and self.store.get_event(event_id).status != "DONE":
                time.sleep(0.05)
            self.assertEqual(self.store.get_event(event_id).status, "DONE",
                             self.store.get_event(event_id).error)
            attempt = self.store.list_attempts()[0]
            self.assertEqual(attempt["state"], "SUCCEEDED")
            self.assertEqual(attempt["outcome"]["return_code"], 0)
            self.assertEqual(len(self.store.list_attempts()), 1)
            self.assertIsNotNone(self.store.get_worker_heartbeat("command"))
        finally:
            worker.terminate()
            try:
                worker.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.communicate(timeout=3)

    def test_worker_crash_fences_attempt_and_stops_child(self) -> None:
        started = self.workspace / "child-started.txt"
        finished = self.workspace / "child-finished.txt"
        (self.workspace / "child_crash.py").write_text(
            f"import time\nfrom pathlib import Path\n"
            f"Path({str(started)!r}).write_text('started')\n"
            f"time.sleep(2)\nPath({str(finished)!r}).write_text('finished')\n",
            encoding="utf-8")
        (self.workspace / "test_crash.py").write_text(
            "import subprocess,sys,time,unittest\n"
            "class Crash(unittest.TestCase):\n"
            "    def test_child(self):\n"
            "        subprocess.Popen([sys.executable,'child_crash.py'])\n"
            "        time.sleep(10)\n", encoding="utf-8")
        req = self.request("worker-crash", action="RUN_CMD", payload={
            "argv": ["python", "-m", "unittest", "test_crash"],
            "idempotency_key": "key:worker-crash"})
        event_id = self.store.append_event(SubstrateEvent(
            type="TOOL_REQUEST", origin_id="command", target_agent="command",
            payload={"request": req}))
        worker = subprocess.Popen(
            [sys.executable, "-m", "appshak_substrate.worker_process",
             "--db-path", str(self.db), "--agent-id", "command",
             "--worktree", str(self.workspace), "--consumer-id", "test-crash-worker",
             "--log-path", str(self.root / "crash.log"),
             "--lease-seconds", "0.3", "--heartbeat-interval-seconds", "0.05"],
            cwd=str(Path(__file__).resolve().parents[1]), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline and not started.exists():
                time.sleep(0.05)
            self.assertTrue(started.exists(), "Child process never reached its start marker")
            worker.kill()
            worker.communicate(timeout=3)
            time.sleep(2.2)
            self.assertFalse(finished.exists(), "Child outlived the crashed worker")
            self.assertEqual(self.store.reconcile_attempts()["fenced_unknown"], 1)
            attempt = self.store.list_attempts()[0]
            self.assertEqual(attempt["state"], "NEEDS_RECONCILIATION")
            self.assertFalse(self.gateway.execute(req).allowed)
            self.assertEqual(self.store.get_event(event_id).status, "CLAIMED")
        finally:
            if worker.poll() is None:
                worker.kill()
            worker.communicate(timeout=3)


if __name__ == "__main__":
    unittest.main()
