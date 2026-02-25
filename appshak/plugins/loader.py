from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from appshak.plugins.interfaces import AppShakPlugin


@dataclass(slots=True)
class PluginLoadError:
    module_name: str
    error: str


class PluginLoader:
    """Dynamic loader that resolves plugin modules without hard coupling."""

    def __init__(
        self,
        module_names: Iterable[str],
        *,
        plugin_config: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self.module_names = [str(name).strip() for name in module_names if str(name).strip()]
        self.plugin_config = plugin_config or {}

    def load(self) -> Tuple[List[AppShakPlugin], List[PluginLoadError]]:
        plugins: List[AppShakPlugin] = []
        errors: List[PluginLoadError] = []
        for requested_name in self.module_names:
            loaded, error = self._load_one(requested_name)
            if loaded is not None:
                plugins.append(loaded)
            elif error is not None:
                errors.append(error)
        return plugins, errors

    def _load_one(self, requested_name: str) -> Tuple[Optional[AppShakPlugin], Optional[PluginLoadError]]:
        tried: List[str] = []
        for module_name in self._module_candidates(requested_name):
            tried.append(module_name)
            try:
                module = importlib.import_module(module_name)
            except Exception as exc:
                last_error = exc
                continue

            factory = getattr(module, "create_plugin", None)
            if not callable(factory):
                return None, PluginLoadError(
                    module_name=requested_name,
                    error=f"Module '{module_name}' is missing callable create_plugin(config).",
                )

            config = (
                self.plugin_config.get(requested_name)
                or self.plugin_config.get(module_name)
                or {}
            )
            try:
                plugin = factory(config)
            except Exception as exc:
                return None, PluginLoadError(
                    module_name=requested_name,
                    error=f"create_plugin failed for '{module_name}': {exc}",
                )

            if not hasattr(plugin, "dispatch") or not callable(getattr(plugin, "dispatch", None)):
                return None, PluginLoadError(
                    module_name=requested_name,
                    error=f"Plugin '{module_name}' does not implement dispatch(state_view).",
                )
            if not hasattr(plugin, "name"):
                return None, PluginLoadError(
                    module_name=requested_name,
                    error=f"Plugin '{module_name}' does not expose name.",
                )
            return plugin, None

        return None, PluginLoadError(
            module_name=requested_name,
            error=f"Could not import plugin module. Tried: {tried}",
        )

    @staticmethod
    def _module_candidates(requested_name: str) -> List[str]:
        if "." in requested_name:
            return [requested_name]
        return [requested_name, f"appshak_plugins.{requested_name}"]

