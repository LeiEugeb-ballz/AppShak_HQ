from __future__ import annotations

HQ_V1 = {
    "map_id": "HQ_v1",
    "bounds": {"w": 100, "h": 60},
    "rooms": {
        "intake_area": {"rect": {"x": 6, "y": 8, "w": 22, "h": 14}},
        "scout_zone": {"rect": {"x": 6, "y": 24, "w": 22, "h": 10}},
        "build_desks": {"rect": {"x": 32, "y": 10, "w": 28, "h": 18}},
        "boardroom": {"rect": {"x": 62, "y": 10, "w": 26, "h": 18}},
        "corner_office": {"rect": {"x": 76, "y": 30, "w": 12, "h": 18}},
        "watercooler": {"rect": {"x": 44, "y": 34, "w": 14, "h": 10}},
        "quarantine": {"rect": {"x": 62, "y": 34, "w": 12, "h": 10}},
        "infra_lane": {"rect": {"x": 32, "y": 34, "w": 10, "h": 18}},
        "unknown_room": {"rect": {"x": 2, "y": 2, "w": 3, "h": 3}},
    },
    "anchors": {
        "intake_area": [{"x": 10, "y": 12}, {"x": 16, "y": 12}, {"x": 22, "y": 12}, {"x": 13, "y": 18}],
        "scout_zone": [{"x": 10, "y": 28}, {"x": 16, "y": 28}, {"x": 22, "y": 28}],
        "build_desks": [
            {"x": 36, "y": 14},
            {"x": 44, "y": 14},
            {"x": 52, "y": 14},
            {"x": 36, "y": 22},
            {"x": 44, "y": 22},
            {"x": 52, "y": 22},
        ],
        "boardroom": [
            {"x": 68, "y": 16},
            {"x": 74, "y": 16},
            {"x": 80, "y": 16},
            {"x": 68, "y": 22},
            {"x": 74, "y": 22},
            {"x": 80, "y": 22},
        ],
        "corner_office": [{"x": 82, "y": 36}, {"x": 82, "y": 44}],
        "watercooler": [{"x": 48, "y": 38}, {"x": 54, "y": 38}],
        "quarantine": [{"x": 66, "y": 38}, {"x": 70, "y": 38}],
        "infra_lane": [{"x": 36, "y": 40}, {"x": 36, "y": 48}, {"x": 36, "y": 56}],
        "unknown_room": [{"x": 3, "y": 3}],
    },
    "camera": {
        "camera_id": "cam_corner_01",
        "locked": True,
        "style": "security_cam",
        "tilt": 0.62,
        "zoom": 1.0,
    },
}


def assign_room_anchors(room_id: str, origin_ids: list[str]) -> dict[str, dict[str, float]]:
    origin_ids_sorted = sorted(origin_ids)
    anchors = HQ_V1["anchors"].get(room_id) or HQ_V1["anchors"]["unknown_room"]
    out: dict[str, dict[str, float]] = {}
    last = anchors[-1]
    for i, oid in enumerate(origin_ids_sorted):
        anchor = anchors[i] if i < len(anchors) else last
        out[oid] = {"x": float(anchor["x"]), "y": float(anchor["y"])}
    return out
