from __future__ import annotations

import unittest

from appshak.plugins.loader import PluginLoader


class TestPluginLoader(unittest.TestCase):
    def test_loader_returns_errors_without_crashing(self) -> None:
        loader = PluginLoader(["intent_engine", "missing_plugin_module_xyz"])
        plugins, errors = loader.load()

        self.assertEqual(len(plugins), 1)
        self.assertEqual(getattr(plugins[0], "name", ""), "intent_engine")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].module_name, "missing_plugin_module_xyz")
        self.assertIn("Could not import plugin module", errors[0].error)


if __name__ == "__main__":
    unittest.main()
