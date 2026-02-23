from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from appshak_substrate.supervisor import Supervisor
from appshak_substrate.types import SubstrateEvent


class TestSupervisorWorkers(unittest.TestCase):
    def test_restart_and_complete_routed_events(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_supervisor_") as temp_dir:
            root = Path(temp_dir)
            db_path = root / "mailstore.db"
            supervisor = Supervisor(
                db_path=db_path,
                agent_ids=["recon", "forge", "command"],
                log_path=root / "supervisor.jsonl",
                human_log_path=root / "supervisor.log",
                runtime_log_dir=root / "workers",
                claim_timeout=0.05,
                lease_seconds=0.25,
                heartbeat_interval_seconds=0.5,
                heartbeat_timeout_seconds=2.0,
                restart_backoff_seconds=0.2,
                restart_backoff_cap_seconds=1.0,
                restart_window_limit=10,
                restart_window_seconds=300.0,
            )

            runner = threading.Thread(target=supervisor.run, kwargs={"duration_seconds": 20.0}, daemon=True)
            runner.start()

            for _ in range(100):
                if len(supervisor.worker_pids()) == 3:
                    break
                time.sleep(0.05)
            self.assertEqual(len(supervisor.worker_pids()), 3)

            agents = ["recon", "forge", "command"]
            for idx in range(30):
                target = agents[idx % len(agents)]
                supervisor.publish_event(
                    SubstrateEvent(
                        type="TEST_ROUTED_EVENT",
                        origin_id="test",
                        target_agent=target,
                        payload={"target_agent": target, "index": idx},
                    )
                )

            time.sleep(0.4)
            killed = False
            for _ in range(40):
                if supervisor.kill_worker("forge"):
                    killed = True
                    break
                time.sleep(0.05)
            self.assertTrue(killed)

            deadline = time.monotonic() + 15.0
            done_count = 0
            restart_seen = False
            while time.monotonic() < deadline:
                done_events = supervisor.mail_store.list_events(status="DONE")
                done_count = sum(1 for evt in done_events if evt.type == "TEST_ROUTED_EVENT")
                restart_seen = restart_seen or supervisor.restart_count("forge") >= 1
                if done_count >= 30 and restart_seen:
                    break
                time.sleep(0.1)

            supervisor.stop()
            runner.join(timeout=5.0)

            done_events = [
                event for event in supervisor.mail_store.list_events(status="DONE")
                if event.type == "TEST_ROUTED_EVENT"
            ]
            done_ids = [event.event_id for event in done_events if event.event_id is not None]
            self.assertEqual(done_count, 30)
            self.assertEqual(len(done_ids), 30)
            self.assertEqual(len(set(done_ids)), 30)
            self.assertTrue(restart_seen)
            self.assertGreaterEqual(supervisor.restart_count("forge"), 1)
            self.assertFalse(supervisor.is_worker_disabled("forge"))


if __name__ == "__main__":
    unittest.main()
