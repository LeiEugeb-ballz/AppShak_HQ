from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def parse_window_spec(window: str, *, now: datetime) -> timedelta:
    raw = str(window).strip().lower()
    if raw.endswith("d"):
        try:
            return timedelta(days=max(1, int(raw[:-1])))
        except Exception:
            return timedelta(days=7)
    if raw.endswith("h"):
        try:
            return timedelta(hours=max(1, int(raw[:-1])))
        except Exception:
            return timedelta(hours=24)
    if raw.endswith("m"):
        try:
            return timedelta(minutes=max(1, int(raw[:-1])))
        except Exception:
            return timedelta(minutes=60)
    return timedelta(days=7)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def to_timestamp_token(value: str) -> str:
    dt = parse_iso_datetime(value)
    if dt is None:
        return "unknown"
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def nested_contains(value: Any, needle: str) -> bool:
    if isinstance(value, str):
        return value == needle
    if isinstance(value, dict):
        for item in value.values():
            if nested_contains(item, needle):
                return True
    if isinstance(value, list):
        for item in value:
            if nested_contains(item, needle):
                return True
    return False
