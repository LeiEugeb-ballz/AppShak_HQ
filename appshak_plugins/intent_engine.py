from __future__ import annotations

from typing import Any, Dict, Optional

from appshak.plugins.interfaces import StateView
from appshak_plugins.intent_store import IntentStore


class IntentEnginePlugin:
    """Intent Engine v0.1 plugin."""

    name = "intent_engine"

    def __init__(self, *, intent_store: Optional[IntentStore] = None) -> None:
        self.intent_store = intent_store or IntentStore()

    async def dispatch(self, state_view: StateView) -> None:
        snapshot = state_view.snapshot()
        queue_size = _as_int(snapshot.get("event_queue_size"), default=0)
        current_event = snapshot.get("current_event")

        if queue_size <= 0:
            intents = self.intent_store.load_intents()
            dispatch_count = len(intents)
            if dispatch_count <= 0:
                dispatch_count = 1
            await state_view.emit_event(
                {
                    "type": "INTENT_DISPATCH",
                    "origin_id": self.name,
                    "payload": {
                        "dispatch_count": dispatch_count,
                        "intents": intents,
                        "prime_directive_justification": (
                            "Intent dispatch maintains non-zero strategic momentum when queues are empty."
                        ),
                    },
                }
            )

        if not isinstance(current_event, dict):
            return
        if str(current_event.get("type")) != "PROPOSAL":
            return

        payload_raw = current_event.get("payload")
        payload = dict(payload_raw) if isinstance(payload_raw, dict) else {}

        declared_intents = payload.get("declared_intents")
        if not _has_declared_intents(declared_intents):
            await state_view.emit_event(
                {
                    "type": "PROPOSAL_INVALID",
                    "origin_id": self.name,
                    "payload": {
                        "reason": "Missing or empty declared_intents.",
                        "source_event_type": "PROPOSAL",
                        "source_event": current_event,
                        "prime_directive_justification": (
                            "Proposal validation prevents ungrounded execution against strategic intent."
                        ),
                    },
                }
            )
            return

        base_score = _as_float(payload.get("base_score"))
        if base_score is None:
            return

        alignment = _as_float(payload.get("alignment"))
        if alignment is None:
            effective_alignment = 0.1
        else:
            effective_alignment = _clamp(alignment, 0.0, 1.0)
        modified_score = base_score * effective_alignment

        await state_view.emit_event(
            {
                "type": "PROPOSAL_VOTE_MODIFIED",
                "origin_id": self.name,
                "payload": {
                    "base_score": base_score,
                    "alignment": effective_alignment,
                    "modified_score": modified_score,
                    "prime_directive_justification": (
                        "Intent-aligned vote weighting prioritizes proposals matching declared strategy."
                    ),
                },
            }
        )


def create_plugin(config: Optional[Dict[str, Any]] = None) -> IntentEnginePlugin:
    cfg = config or {}
    store_path = cfg.get("intent_store_path")
    if isinstance(store_path, str) and store_path.strip():
        store = IntentStore(path=store_path.strip())
    else:
        store = IntentStore()
    return IntentEnginePlugin(intent_store=store)


def _has_declared_intents(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _as_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))

