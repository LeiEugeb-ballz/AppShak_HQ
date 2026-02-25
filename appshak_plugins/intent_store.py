from __future__ import annotations

import json
from pathlib import Path
from typing import List


class IntentStore:
    """JSON-backed intent persistence for intent engine plugin."""

    DEFAULT_INTENTS = ["maintain_operational_continuity"]

    def __init__(self, path: str | Path = ".appshak/intents.json") -> None:
        self.path = Path(path)

    def load_intents(self) -> List[str]:
        if not self.path.exists():
            self.save_intents(self.DEFAULT_INTENTS)
            return list(self.DEFAULT_INTENTS)

        try:
            raw = self.path.read_text(encoding="utf-8")
            loaded = json.loads(raw)
        except Exception:
            self.save_intents(self.DEFAULT_INTENTS)
            return list(self.DEFAULT_INTENTS)

        if not isinstance(loaded, dict):
            self.save_intents(self.DEFAULT_INTENTS)
            return list(self.DEFAULT_INTENTS)

        intents_raw = loaded.get("intents")
        if not isinstance(intents_raw, list):
            self.save_intents(self.DEFAULT_INTENTS)
            return list(self.DEFAULT_INTENTS)

        intents = [str(item).strip() for item in intents_raw if isinstance(item, str) and item.strip()]
        if not intents:
            intents = list(self.DEFAULT_INTENTS)
            self.save_intents(intents)
        return intents

    def save_intents(self, intents: List[str]) -> None:
        normalized = [str(item).strip() for item in intents if isinstance(item, str) and str(item).strip()]
        payload = {"intents": normalized}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

