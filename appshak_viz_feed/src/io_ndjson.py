from __future__ import annotations

import json
from typing import Any, Dict, Iterator


def read_ndjson(path: str) -> Iterator[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            yield json.loads(stripped)


def write_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
