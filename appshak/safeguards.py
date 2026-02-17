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

    async def run_diagnostics(self) -> bool:
        async with self._lock:
            return self.retry_max > 0 and self.cooldown_seconds >= 0

    async def check_request(self, event: Any, origin_id: str) -> Dict[str, Any]:
        payload = self._payload(event)
        endpoint = self._extract_endpoint(payload)
        action_key = self._action_key(payload, origin_id, endpoint)

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

    def _is_whitelisted(self, endpoint: str) -> bool:
        if not self.endpoint_whitelist:
            return False
        return self._normalize_host(endpoint) in self.endpoint_whitelist

    @staticmethod
    def _payload(event: Any) -> Dict[str, Any]:
        if isinstance(event, dict):
            payload = event.get("payload", {})
            return payload if isinstance(payload, dict) else {}
        payload = getattr(event, "payload", {})
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _extract_endpoint(payload: Dict[str, Any]) -> str:
        endpoint = payload.get("endpoint") or payload.get("url")
        return str(endpoint).strip() if endpoint else ""

    @staticmethod
    def _normalize_host(endpoint: str) -> str:
        raw = str(endpoint).strip().lower()
        if not raw:
            return raw
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        return parsed.netloc or parsed.path

    def _contains_monetary_operation(self, payload: Dict[str, Any]) -> bool:
        payload_keys = {str(key).lower() for key in payload.keys()}
        action_text = str(payload.get("action", "")).lower()
        joined = f"{action_text} {' '.join(payload_keys)}"
        return any(keyword in joined for keyword in self._MONETARY_KEYWORDS)

    def _contains_shell_execution(self, payload: Dict[str, Any]) -> bool:
        for field in self._SHELL_FIELDS:
            value = payload.get(field)
            if isinstance(value, str) and value.strip():
                return True
        return False

    @staticmethod
    def _action_key(payload: Dict[str, Any], origin_id: str, endpoint: str) -> str:
        explicit = payload.get("action_id")
        if explicit:
            return str(explicit)
        action = str(payload.get("action", "external_action"))
        return f"{origin_id}|{action}|{endpoint}"
