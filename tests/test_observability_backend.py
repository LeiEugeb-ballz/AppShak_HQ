from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from appshak.event_bus import EventBus
from appshak.plugins.runtime import KernelStateView
from appshak_observability.broadcaster import ObservabilityBroadcaster
from appshak_observability.models import (
    CHANNEL_INTENT_DISPATCH_EVENTS,
    CHANNEL_RESTART_EVENTS,
    CHANNEL_TOOL_EXECUTION_LOGS,
    SnapshotResponse,
)
from appshak_observability.server import create_app
from appshak_substrate.bus_adapter import DurableEventBus
from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.types import SubstrateEvent


class _FakeStateView:
    def snapshot(self) -> dict:
        return {
            "running": True,
            "event_queue_size": "7",
            "current_event": {
                "type": "AGENT_STATUS",
                "timestamp": "2026-02-25T00:00:00+00:00",
                "origin_id": "recon",
                "payload": {"status": "ok"},
            },
            "timestamp": "2026-02-25T00:00:01+00:00",
        }


class TestObservabilitySnapshotEndpoint(unittest.TestCase):
    def test_snapshot_endpoint_uses_stable_contract(self) -> None:
        app = create_app(
            state_view=_FakeStateView(),
            snapshot_poll_interval=60.0,
            durable_poll_interval=60.0,
        )
        routes = [route for route in app.routes if getattr(route, "path", "") == "/api/snapshot"]
        self.assertEqual(len(routes), 1)
        payload = _model_to_dict(asyncio.run(routes[0].endpoint()))
        self.assertEqual(sorted(payload.keys()), ["current_event", "event_queue_size", "running", "timestamp"])
        self.assertTrue(payload["running"])
        self.assertEqual(payload["event_queue_size"], 7)
        self.assertEqual(payload["current_event"]["type"], "AGENT_STATUS")

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
    async def test_streams_intent_dispatch_from_publish_hook(self) -> None:
        bus = EventBus()
        kernel = SimpleNamespace(running=True, event_bus=bus)
        state_view = KernelStateView(kernel)
        broadcaster = ObservabilityBroadcaster(
            state_view=state_view,
            event_bus=bus,
            snapshot_poll_interval=60.0,
            durable_poll_interval=60.0,
        )
        await broadcaster.start()
        queue = broadcaster.subscribe()
        try:
            await bus.publish(
                {
                    "type": "INTENT_DISPATCH",
                    "origin_id": "intent_engine",
                    "payload": {
                        "dispatch_count": 1,
                        "prime_directive_justification": "test",
                    },
                }
            )
            event = await self._wait_for_channel(queue, CHANNEL_INTENT_DISPATCH_EVENTS)
            self.assertEqual(event.channel, CHANNEL_INTENT_DISPATCH_EVENTS)
            self.assertEqual(event.data["event"]["type"], "INTENT_DISPATCH")
        finally:
            broadcaster.unsubscribe(queue)
            await broadcaster.stop()

    async def test_streams_restart_and_tool_logs_from_durable_bus(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_observability_") as temp_dir:
            db_path = Path(temp_dir) / "mailstore.db"
            mail_store = SQLiteMailStore(db_path, lease_seconds=0.25)
            bus = DurableEventBus(
                mail_store=mail_store,
                consumer_id="observability-test",
                include_unrouted=True,
                lease_seconds=0.25,
            )
            kernel = SimpleNamespace(running=False, event_bus=bus)
            state_view = KernelStateView(kernel)
            broadcaster = ObservabilityBroadcaster(
                state_view=state_view,
                event_bus=bus,
                snapshot_poll_interval=60.0,
                durable_poll_interval=0.05,
            )
            await broadcaster.start()
            queue = broadcaster.subscribe()
            try:
                await asyncio.sleep(0.1)
                mail_store.append_event(
                    SubstrateEvent(
                        type="WORKER_RESTARTED",
                        origin_id="supervisor",
                        target_agent="command",
                        payload={"agent_id": "forge"},
                    )
                )
                mail_store.append_tool_audit(
                    agent_id="forge",
                    action_type="RUN_CMD",
                    working_dir=str(Path(temp_dir)),
                    idempotency_key="obs-test-key",
                    allowed=True,
                    reason="ok",
                    payload={"argv": ["echo", "hello"]},
                    result={"return_code": 0, "stdout": "hello"},
                    correlation_id="corr-1",
                )

                restart_event = await self._wait_for_channel(queue, CHANNEL_RESTART_EVENTS, timeout=4.0)
                self.assertEqual(restart_event.data["event"]["type"], "WORKER_RESTARTED")

                tool_event = await self._wait_for_channel(queue, CHANNEL_TOOL_EXECUTION_LOGS, timeout=4.0)
                self.assertIn("audit", tool_event.data)
                self.assertEqual(tool_event.data["audit"]["action_type"], "RUN_CMD")
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


def _model_to_dict(model: object) -> dict:
    dump = getattr(model, "model_dump", None)
    if callable(dump):
        return dict(dump())
    as_dict = getattr(model, "dict", None)
    if callable(as_dict):
        return dict(as_dict())
    return dict(model)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
