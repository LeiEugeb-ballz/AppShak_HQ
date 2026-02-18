from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.parse import urlparse


class SafeguardMonitor:
    """Security governor for external action gating and sandbox execution."""

    _MONETARY_KEYWORDS = {
        "pay",
        "payment",
        "charge",
        "billing",
        "invoice",
        "wire",
        "transfer",
        "withdraw",
        "deposit",
        "bank",
        "wallet",
        "crypto",
        "money",
        "usd",
        "eur",
    }

    _SHELL_FIELDS = {"command", "shell", "shell_command", "exec", "script", "process"}
    _SAFE_METHODS = {"SIMULATE", "NOOP"}

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.retry_max = int(config.get("safeguard_retry_max", 3))
        self.cooldown_seconds = int(config.get("cooldown_timer_seconds", config.get("safeguard_cooldown_seconds", 60)))
        configured = config.get("endpoint_whitelist", [])
        self.endpoint_whitelist = {
            self._normalize_host(str(item))
            for item in configured
            if str(item).strip()
        }

        self._lock = asyncio.Lock()
        self._attempt_state: Dict[str, Dict[str, float]] = {}
        self.allow_real_world_impact = bool(config.get("allow_real_world_impact", False))

    async def run_diagnostics(self) -> bool:
        async with self._lock:
            return self.retry_max > 0 and self.cooldown_seconds >= 0

    async def check_request(self, event: Any, origin_id: str) -> Dict[str, Any]:
        payload = self._payload(event)
        endpoint = self._extract_endpoint(payload)
        action_key = self._action_key(payload, origin_id, endpoint)
        method = str(payload.get("method", "SIMULATE")).upper()
        simulate_flag = payload.get("simulate")

        cooldown_status = await self._cooldown_status(action_key)
        if cooldown_status["in_cooldown"]:
            return {
                "allowed": False,
                "reason": "Action in cooldown window.",
                "action_key": action_key,
                "endpoint": endpoint,
                "origin_id": origin_id,
                "cooldown_until": cooldown_status["cooldown_until"],
            }

        if self._contains_monetary_operation(payload):
            return {
                "allowed": False,
                "reason": "Monetary operations are prohibited by safeguard policy.",
                "action_key": action_key,
                "endpoint": endpoint,
                "origin_id": origin_id,
            }

        if self._contains_shell_execution(payload):
            return {
                "allowed": False,
                "reason": "Shell execution is prohibited by safeguard policy.",
                "action_key": action_key,
                "endpoint": endpoint,
                "origin_id": origin_id,
            }

        if not self.allow_real_world_impact:
            if method not in self._SAFE_METHODS:
                return {
                    "allowed": False,
                    "reason": "Real-world execution methods are blocked by safeguard policy.",
                    "action_key": action_key,
                    "endpoint": endpoint,
                    "origin_id": origin_id,
                    "method": method,
                }
            if simulate_flag is False:
                return {
                    "allowed": False,
                    "reason": "simulate=false is blocked by safeguard policy.",
                    "action_key": action_key,
                    "endpoint": endpoint,
                    "origin_id": origin_id,
                }

        if not endpoint:
            return {
                "allowed": False,
                "reason": "External action request missing endpoint.",
                "action_key": action_key,
                "endpoint": endpoint,
                "origin_id": origin_id,
            }

        if not self._is_whitelisted(endpoint):
            return {
                "allowed": False,
                "reason": "Endpoint is not in whitelist.",
                "action_key": action_key,
                "endpoint": endpoint,
                "origin_id": origin_id,
            }

        return {
            "allowed": True,
            "reason": "Safeguard checks passed.",
            "action_key": action_key,
            "endpoint": endpoint,
            "origin_id": origin_id,
        }

    async def execute_in_sandbox(self, event: Any, origin_id: str) -> Dict[str, Any]:
        """Sandbox executor: no shell, no monetary actions, no unrestricted execution."""
        payload = self._payload(event)
        endpoint = self._extract_endpoint(payload)
        action = str(payload.get("action", "external_action"))
        method = str(payload.get("method", "SIMULATE")).upper()
        simulate_flag = payload.get("simulate")

        if self._contains_shell_execution(payload):
            return {
                "success": False,
                "status": "denied",
                "reason": "Shell execution denied in sandbox.",
                "origin_id": origin_id,
                "endpoint": endpoint,
                "action": action,
            }

        if self._contains_monetary_operation(payload):
            return {
                "success": False,
                "status": "denied",
                "reason": "Monetary operation denied in sandbox.",
                "origin_id": origin_id,
                "endpoint": endpoint,
                "action": action,
            }

        if method not in {"SIMULATE", "NOOP"}:
            return {
                "success": False,
                "status": "denied",
                "reason": "Only SIMULATE/NOOP methods are allowed in the sandbox.",
                "origin_id": origin_id,
                "endpoint": endpoint,
                "action": action,
                "method": method,
            }
        if simulate_flag is False:
            return {
                "success": False,
                "status": "denied",
                "reason": "simulate=false denied in sandbox.",
                "origin_id": origin_id,
                "endpoint": endpoint,
                "action": action,
                "method": method,
            }

        return {
            "success": True,
            "status": "executed",
            "reason": "Sandbox simulation completed.",
            "origin_id": origin_id,
            "endpoint": endpoint,
            "action": action,
            "method": method,
        }

    async def record_attempt(self, event: Any, origin_id: str, success: bool) -> Dict[str, Any]:
        payload = self._payload(event)
        endpoint = self._extract_endpoint(payload)
        action_key = self._action_key(payload, origin_id, endpoint)

        async with self._lock:
            now = time.time()
            state = self._attempt_state.setdefault(action_key, {"retries": 0.0, "cooldown_until": 0.0})

            if success:
                state["retries"] = 0.0
                state["cooldown_until"] = 0.0
            else:
                state["retries"] = float(int(state.get("retries", 0.0)) + 1)
                if int(state["retries"]) >= self.retry_max:
                    state["cooldown_until"] = now + self.cooldown_seconds
                    state["retries"] = float(self.retry_max)

            cooldown_until = float(state.get("cooldown_until", 0.0))
            return {
                "action_key": action_key,
                "retries": int(state.get("retries", 0.0)),
                "cooldown_until": (
                    datetime.fromtimestamp(cooldown_until, tz=timezone.utc).isoformat()
                    if cooldown_until > 0
                    else None
                ),
            }

    async def _cooldown_status(self, action_key: str) -> Dict[str, Any]:
        async with self._lock:
            state = self._attempt_state.setdefault(action_key, {"retries": 0.0, "cooldown_until": 0.0})
            now = time.time()
            cooldown_until = float(state.get("cooldown_until", 0.0))
            return {
                "in_cooldown": cooldown_until > now,
                "cooldown_until": (
                    datetime.fromtimestamp(cooldown_until, tz=timezone.utc).isoformat()
                    if cooldown_until > 0
                    else None
                ),
            }

    def _payload(self, event: Any) -> Dict[str, Any]:
        return event.to_dict().get("payload", {}) if hasattr(event, "to_dict") else event.get("payload", {})

    def _extract_endpoint(self, payload: Dict[str, Any]) -> str:
        return str(payload.get("endpoint") or payload.get("url") or "")

    def _action_key(self, payload: Dict[str, Any], origin_id: str, endpoint: str) -> str:
        action = payload.get("action", "default")
        return f"{origin_id}:{action}:{endpoint}"

    def _contains_monetary_operation(self, payload: Dict[str, Any]) -> bool:
        text = str(payload).lower()
        return any(kw in text for kw in self._MONETARY_KEYWORDS)

    def _contains_shell_execution(self, payload: Dict[str, Any]) -> bool:
        return any(k in payload for k in self._SHELL_FIELDS)

    def _normalize_host(self, url: str) -> str:
        try:
            return urlparse(url).netloc or url
        except Exception:
            return url

    def _is_whitelisted(self, endpoint: str) -> bool:
        host = self._normalize_host(endpoint)
        return host in self.endpoint_whitelist
