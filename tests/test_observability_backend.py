from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from appshak_observability.broadcaster import ObservabilityBroadcaster
from appshak_observability.models import CHANNEL_VIEW_UPDATE, SnapshotResponse
from appshak_observability.server import create_app
from appshak_projection.view_store import ProjectionViewStore


class _FakeStateView:
    def snapshot(self) -> dict:
        return {
            "schema_version": 1,
            "running": True,
            "event_queue_size": 7,
            "derived": {"office_mode": "RUNNING", "stress_level": 0.28},
            "workers": {"recon": {"state": "ACTIVE"}},
            "current_event": {
                "type": "AGENT_STATUS",
                "timestamp": "2026-02-25T00:00:00+00:00",
                "origin_id": "recon",
                "payload": {"status": "ok"},
            },
            "timestamp": "2026-02-25T00:00:01+00:00",
            "last_seen_event_id": 7,
            "last_seen_tool_audit_id": 0,
            "event_type_counts": {"AGENT_STATUS": 7},
            "tool_audit_counts": {"allowed": 0, "denied": 0},
        }


class TestObservabilitySnapshotEndpoint(unittest.TestCase):
    def test_snapshot_endpoint_returns_projection_view(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_observability_snapshot_") as temp_dir:
            projection_store = ProjectionViewStore(Path(temp_dir) / "view.json")
            projection_store.save(_FakeStateView().snapshot())

            app = create_app(
                state_view=_FakeStateView(),
                projection_view_store=projection_store,
                snapshot_poll_interval=60.0,
                durable_poll_interval=60.0,
            )
            routes = [route for route in app.routes if getattr(route, "path", "") == "/api/snapshot"]
            self.assertEqual(len(routes), 1)
            payload = asyncio.run(routes[0].endpoint())

            self.assertEqual(payload["schema_version"], 1)
            self.assertTrue(payload["running"])
            self.assertIn("workers", payload)
            self.assertIn("derived", payload)
            self.assertIn("event_type_counts", payload)
            self.assertIn("tool_audit_counts", payload)

    def test_snapshot_model_normalizes_invalid_payload(self) -> None:
        normalized = SnapshotResponse.from_snapshot(
            {
                "running": "yes",
                "event_queue_size": "not-an-int",
                "current_event": {"type": "AGENT_STATUS", "payload": {"raw": Path("x.txt")}},
            }
        )
        self.assertTrue(normalized.running)
        self.assertEqual(normalized.event_queue_size, 0)
        self.assertEqual(normalized.current_event.payload["raw"], "x.txt")


class TestObservabilityBroadcaster(unittest.IsolatedAsyncioTestCase):
    async def test_streams_view_update_when_projection_changes(self) -> None:
        class _MutableProjectionStore:
            def __init__(self) -> None:
                self.view = {
                    "schema_version": 1,
                    "running": False,
                    "event_queue_size": 0,
                    "timestamp": "2026-02-25T00:00:01+00:00",
                    "last_seen_event_id": 0,
                    "last_seen_tool_audit_id": 0,
                }

            def load(self) -> dict:
                return dict(self.view)

        projection_store = _MutableProjectionStore()
        broadcaster = ObservabilityBroadcaster(
            state_view=_FakeStateView(),
            projection_view_store=projection_store,
            snapshot_poll_interval=0.05,
            durable_poll_interval=60.0,
        )
        await broadcaster.start()
        queue = broadcaster.subscribe()
        try:
            first = await self._wait_for_channel(queue, CHANNEL_VIEW_UPDATE, timeout=2.0)
            self.assertEqual(first.channel, CHANNEL_VIEW_UPDATE)

            projection_store.view = {
                "schema_version": 1,
                "running": True,
                "event_queue_size": 1,
                "timestamp": "2026-02-25T00:00:02+00:00",
                "last_seen_event_id": 1,
                "last_seen_tool_audit_id": 0,
            }
            updated = await self._wait_for_channel(queue, CHANNEL_VIEW_UPDATE, timeout=2.0)
            self.assertEqual(updated.channel, CHANNEL_VIEW_UPDATE)
            self.assertEqual(updated.data["view"]["last_seen_event_id"], 1)
        finally:
            broadcaster.unsubscribe(queue)
            await broadcaster.stop()

    async def test_streams_view_update_only(self) -> None:
        class _StaticProjectionStore:
            def load(self) -> dict:
                return {
                    "schema_version": 1,
                    "running": False,
                    "event_queue_size": 0,
                    "timestamp": "2026-02-25T00:00:01+00:00",
                    "last_seen_event_id": 0,
                    "last_seen_tool_audit_id": 0,
                }

        broadcaster = ObservabilityBroadcaster(
            state_view=_FakeStateView(),
            projection_view_store=_StaticProjectionStore(),
            snapshot_poll_interval=0.05,
            durable_poll_interval=60.0,
        )
        await broadcaster.start()
        queue = broadcaster.subscribe()
        try:
            envelope = await asyncio.wait_for(queue.get(), timeout=2.0)
            self.assertEqual(envelope.channel, CHANNEL_VIEW_UPDATE)
        finally:
            broadcaster.unsubscribe(queue)
            await broadcaster.stop()

    async def _wait_for_channel(
        self,
        queue: "asyncio.Queue",
        channel: str,
        *,
        timeout: float = 2.0,
    ):
        deadline = asyncio.get_running_loop().time() + max(0.1, timeout)
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                self.fail(f"Timed out waiting for channel={channel}")
            envelope = await asyncio.wait_for(queue.get(), timeout=remaining)
            if getattr(envelope, "channel", None) == channel:
                return envelope


if __name__ == "__main__":
    unittest.main()
