from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional

from .constants import WATER_COOLER_IDLE_STRESS_MAX, WATER_COOLER_MAX_RECIPIENTS
from .registry import AgentRegistry
from .utils import as_float, as_int, canonical_hash, normalize_agent_id


@dataclass(frozen=True)
class WaterCoolerLesson:
    lesson_id: str
    schema_version: int
    source_event_type: str
    source_event_id: int
    source_timestamp: str
    source_agent: str
    tags: List[str]
    summary: str
    confidence: float
    recipients: List[str]

    def as_dict(self) -> Dict[str, object]:
        return {
            "lesson_id": self.lesson_id,
            "schema_version": self.schema_version,
            "source_event_type": self.source_event_type,
            "source_event_id": self.source_event_id,
            "source_timestamp": self.source_timestamp,
            "source_agent": self.source_agent,
            "tags": list(self.tags),
            "summary": self.summary,
            "confidence": self.confidence,
            "recipients": list(self.recipients),
        }


class WaterCoolerPropagation:
    LESSON_SCHEMA_VERSION = 1

    def maybe_propagate(
        self,
        *,
        registry: AgentRegistry,
        previous_view: Mapping[str, object] | None,
        current_view: Mapping[str, object] | None,
    ) -> Dict[str, object]:
        previous = previous_view if isinstance(previous_view, Mapping) else {}
        current = current_view if isinstance(current_view, Mapping) else {}

        if not self._idle_trigger(previous=previous, current=current):
            return {"triggered": False, "lesson": None, "propagation_metric": 0.0}

        current_event = current.get("current_event")
        if not isinstance(current_event, Mapping):
            return {"triggered": False, "lesson": None, "propagation_metric": 0.0}

        source_event_id = as_int(current.get("last_seen_event_id"), default=0)
        source_event_type = str(current_event.get("type", "")).strip().upper() or "UNKNOWN"
        source_timestamp = str(current_event.get("timestamp", "")).strip()
        source_agent = self._source_agent(current_event=current_event, registry=registry)

        recipients = [agent_id for agent_id in registry.agent_ids if agent_id != source_agent]
        recipients = recipients[:WATER_COOLER_MAX_RECIPIENTS]

        lesson_id = canonical_hash(
            {
                "source_event_id": source_event_id,
                "source_event_type": source_event_type,
                "source_agent": source_agent,
                "registry_version": registry.version,
                "recipients": recipients,
            }
        )

        lesson = WaterCoolerLesson(
            lesson_id=lesson_id,
            schema_version=self.LESSON_SCHEMA_VERSION,
            source_event_type=source_event_type,
            source_event_id=source_event_id,
            source_timestamp=source_timestamp,
            source_agent=source_agent,
            tags=["governance", "water_cooler", source_event_type.lower()],
            summary=f"Idle-window lesson from {source_event_type} for deterministic governance memory.",
            confidence=0.65,
            recipients=recipients,
        )

        for agent_id in recipients:
            registry.add_lesson_reference(agent_id, lesson.lesson_id)

        propagation_metric = 0.0
        if registry.agent_ids:
            propagation_metric = float(len(recipients)) / float(len(registry.agent_ids))
        return {
            "triggered": True,
            "lesson": lesson.as_dict(),
            "propagation_metric": propagation_metric,
        }

    @staticmethod
    def _idle_trigger(*, previous: Mapping[str, object], current: Mapping[str, object]) -> bool:
        prev_event_id = as_int(previous.get("last_seen_event_id"), default=0)
        curr_event_id = as_int(current.get("last_seen_event_id"), default=0)
        if curr_event_id <= prev_event_id:
            return False

        derived = current.get("derived")
        if not isinstance(derived, Mapping):
            return False
        office_mode = str(derived.get("office_mode", "")).strip().upper()
        stress_level = as_float(derived.get("stress_level"), default=1.0)
        if office_mode != "PAUSED":
            return False
        if stress_level > WATER_COOLER_IDLE_STRESS_MAX:
            return False
        return True

    @staticmethod
    def _source_agent(*, current_event: Mapping[str, object], registry: AgentRegistry) -> str:
        payload = current_event.get("payload")
        if isinstance(payload, Mapping):
            for key in ("target_agent", "agent_id", "worker"):
                candidate = normalize_agent_id(payload.get(key))
                if candidate and registry.has_agent(candidate):
                    return candidate
        origin = normalize_agent_id(current_event.get("origin_id"))
        if origin and registry.has_agent(origin):
            return origin
        return registry.agent_ids[0] if registry.agent_ids else "unknown"
