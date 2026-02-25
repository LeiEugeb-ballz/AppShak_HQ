from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from appshak_plugins.intent_engine import create_plugin
from appshak_plugins.intent_store import IntentStore


class _FakeStateView:
    def __init__(self, snapshot_data: Dict[str, Any]) -> None:
        self._snapshot_data = snapshot_data
        self.emitted: List[Dict[str, Any]] = []

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._snapshot_data)

    async def emit_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        self.emitted.append(dict(event))
        return event


class TestIntentEnginePlugin(unittest.TestCase):
    def test_non_zero_dispatch_and_intent_store_file_created_when_queue_empty(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_intent_plugin_") as temp_dir:
            store_path = Path(temp_dir) / ".appshak" / "intents.json"
            plugin = create_plugin({"intent_store_path": str(store_path)})
            state_view = _FakeStateView({"event_queue_size": 0, "current_event": None})

            asyncio.run(plugin.dispatch(state_view))

            self.assertTrue(store_path.exists())
            dispatch_events = [evt for evt in state_view.emitted if evt.get("type") == "INTENT_DISPATCH"]
            self.assertEqual(len(dispatch_events), 1)
            payload = dispatch_events[0].get("payload", {})
            self.assertGreater(int(payload.get("dispatch_count", 0)), 0)

    def test_proposal_gate_emits_invalid_when_declared_intents_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_intent_gate_") as temp_dir:
            plugin = create_plugin({"intent_store_path": str(Path(temp_dir) / ".appshak" / "intents.json")})
            state_view = _FakeStateView(
                {
                    "event_queue_size": 1,
                    "current_event": {
                        "type": "PROPOSAL",
                        "origin_id": "recon",
                        "payload": {"base_score": 0.8, "alignment": 0.7},
                    },
                }
            )

            asyncio.run(plugin.dispatch(state_view))

            invalid_events = [evt for evt in state_view.emitted if evt.get("type") == "PROPOSAL_INVALID"]
            self.assertEqual(len(invalid_events), 1)

    def test_vote_modifier_uses_alignment_when_present(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_intent_vote_") as temp_dir:
            plugin = create_plugin({"intent_store_path": str(Path(temp_dir) / ".appshak" / "intents.json")})
            state_view = _FakeStateView(
                {
                    "event_queue_size": 2,
                    "current_event": {
                        "type": "PROPOSAL",
                        "origin_id": "recon",
                        "payload": {
                            "declared_intents": ["build"],
                            "base_score": 10.0,
                            "alignment": 0.35,
                        },
                    },
                }
            )

            asyncio.run(plugin.dispatch(state_view))

            vote_events = [evt for evt in state_view.emitted if evt.get("type") == "PROPOSAL_VOTE_MODIFIED"]
            self.assertEqual(len(vote_events), 1)
            payload = vote_events[0].get("payload", {})
            self.assertAlmostEqual(float(payload.get("modified_score", 0.0)), 3.5)

    def test_vote_modifier_uses_point_one_when_alignment_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_intent_vote_default_") as temp_dir:
            plugin = create_plugin({"intent_store_path": str(Path(temp_dir) / ".appshak" / "intents.json")})
            state_view = _FakeStateView(
                {
                    "event_queue_size": 2,
                    "current_event": {
                        "type": "PROPOSAL",
                        "origin_id": "recon",
                        "payload": {
                            "declared_intents": ["build"],
                            "base_score": 5.0,
                        },
                    },
                }
            )

            asyncio.run(plugin.dispatch(state_view))

            vote_events = [evt for evt in state_view.emitted if evt.get("type") == "PROPOSAL_VOTE_MODIFIED"]
            self.assertEqual(len(vote_events), 1)
            payload = vote_events[0].get("payload", {})
            self.assertAlmostEqual(float(payload.get("modified_score", 0.0)), 0.5)


class TestIntentStore(unittest.TestCase):
    def test_store_uses_dot_appshak_intents_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_intent_store_") as temp_dir:
            path = Path(temp_dir) / ".appshak" / "intents.json"
            store = IntentStore(path=path)
            intents = store.load_intents()
            self.assertTrue(path.exists())
            self.assertGreater(len(intents), 0)
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("intents", raw)


if __name__ == "__main__":
    unittest.main()
