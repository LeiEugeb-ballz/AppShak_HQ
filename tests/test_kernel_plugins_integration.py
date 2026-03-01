from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from appshak import AppShakKernel


class TestKernelPluginsIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_missing_plugin_is_recorded_not_raised(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_kernel_plugin_") as temp_dir:
            kernel = AppShakKernel(
                {
                    "memory_root": str(Path(temp_dir) / "state"),
                    "heartbeat_interval": 0.01,
                    "event_poll_timeout": 0.01,
                    "plugin_modules": ["missing_plugin_for_test_xyz"],
                }
            )

            self.assertEqual(len(kernel.plugin_load_errors), 1)
            self.assertEqual(kernel.plugin_load_errors[0].module_name, "missing_plugin_for_test_xyz")

            runner = asyncio.create_task(kernel.start())
            await asyncio.sleep(0.05)
            await kernel.shutdown()
            if not runner.done():
                runner.cancel()
                await asyncio.gather(runner, return_exceptions=True)

    async def test_intent_engine_plugin_loads(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appshak_kernel_plugin_") as temp_dir:
            intent_store = Path(temp_dir) / ".appshak" / "intents.json"
            kernel = AppShakKernel(
                {
                    "memory_root": str(Path(temp_dir) / "state"),
                    "heartbeat_interval": 0.01,
                    "event_poll_timeout": 0.01,
                    "plugin_modules": ["intent_engine"],
                    "plugin_config": {"intent_engine": {"intent_store_path": str(intent_store)}},
                }
            )

            self.assertEqual(len(kernel.plugin_load_errors), 0)
            self.assertGreaterEqual(len(kernel.plugins), 1)
            intent_plugin = next(
                (plugin for plugin in kernel.plugins if getattr(plugin, "name", "") == "intent_engine"),
                None,
            )
            self.assertIsNotNone(intent_plugin)
            self.assertEqual(intent_plugin.intent_store.path, intent_store)

            runner = asyncio.create_task(kernel.start())
            await asyncio.sleep(0.05)
            await kernel.shutdown()
            if not runner.done():
                runner.cancel()
                await asyncio.gather(runner, return_exceptions=True)

            intent_plugin.intent_store.load_intents()
            self.assertTrue(intent_store.exists())


if __name__ == "__main__":
    unittest.main()
