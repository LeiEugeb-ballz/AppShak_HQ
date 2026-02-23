from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.types import SubstrateEvent


class TestMailstoreDurable(unittest.TestCase):
    def test_publish_consume_crash_recovery_no_duplicates(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_mailstore_") as temp_dir:
            db_path = Path(temp_dir) / "mailstore.db"
            store = SQLiteMailStore(db_path, lease_seconds=0.25, poll_interval=0.01)

            for idx in range(100):
                store.append_event(
                    SubstrateEvent(
                        type="TEST_EVENT",
                        origin_id="test",
                        target_agent="recon",
                        payload={"index": idx, "target_agent": "recon"},
                    )
                )

            acked_ids: list[int] = []
            for idx in range(50):
                event = store.claim_next_event(
                    "consumer_a",
                    timeout=1.0,
                    target_agent="recon",
                    include_unrouted=False,
                )
                self.assertIsNotNone(event)
                assert event is not None
                self.assertIsNotNone(event.event_id)
                assert event.event_id is not None
                if idx == 49:
                    # Simulate consumer crash by not acking this lease.
                    break
                store.ack_event(event.event_id, consumer_id="consumer_a")
                acked_ids.append(event.event_id)

            time.sleep(0.35)

            while True:
                event = store.claim_next_event(
                    "consumer_b",
                    timeout=0.1,
                    target_agent="recon",
                    include_unrouted=False,
                )
                if event is None:
                    break
                self.assertIsNotNone(event.event_id)
                assert event.event_id is not None
                store.ack_event(event.event_id, consumer_id="consumer_b")
                acked_ids.append(event.event_id)

            status_counts = store.status_counts()
            self.assertEqual(status_counts.get("DONE", 0), 100)
            self.assertEqual(len(acked_ids), 100)
            self.assertEqual(len(set(acked_ids)), 100)


if __name__ == "__main__":
    unittest.main()
