from __future__ import annotations

from typing import Optional


def derive_room(
    *,
    phase: Optional[str],
    outcome: Optional[str],
    activity: Optional[str],
    origin_role: str,
    room_hint: Optional[str],
) -> str:
    if outcome in {"BLOCKED", "DENIED"}:
        return "quarantine"

    if phase == "RECOVERY" or activity == "RECOVERY":
        return "infra_lane" if origin_role == "KERNEL" else "build_desks"

    if phase == "INTAKE":
        return "scout_zone" if origin_role == "SCOUT" else "intake_area"
    if phase == "BUILD":
        return "build_desks"
    if phase == "APPROVAL":
        return "boardroom"
    if phase == "BLOCKED":
        return "quarantine"
    if phase == "ERROR":
        return "build_desks"

    if isinstance(room_hint, str) and room_hint.strip():
        hint = room_hint.strip().lower()
        hint_map = {
            "office": "intake_area",
            "build_room": "build_desks",
            "boardroom": "boardroom",
            "kernel_room": "infra_lane",
        }
        if hint in hint_map:
            return hint_map[hint]

    return "unknown_room"


def derive_state(*, phase: Optional[str], outcome: Optional[str], activity: Optional[str]) -> str:
    if activity == "RECOVERY":
        return "RECOVERY"
    if outcome in {"BLOCKED", "DENIED"}:
        return "BLOCKED"
    if outcome == "FAILED" or phase == "ERROR":
        return "ERROR"
    if phase == "INTAKE":
        return "INTAKE"
    if phase == "BUILD":
        return "BUILD"
    if phase == "APPROVAL":
        return "APPROVAL"
    if activity == "IDLE":
        return "IDLE"
    return "UNKNOWN"
