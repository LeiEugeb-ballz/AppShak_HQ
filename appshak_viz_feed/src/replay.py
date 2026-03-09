from __future__ import annotations

import argparse
import hashlib
import json
import os
from typing import Any, Dict, List

from .io_ndjson import read_ndjson, write_json
from .reducer import initial_state, reduce_event
from .replay_summary import build_replay_summary, to_dict as summary_to_dict


def _hash_json_obj(obj: Any) -> str:
    encoded = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(prog="appshak_viz_feed.replay")
    parser.add_argument("--run", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--emit-projection-snapshot", action="store_true")
    parser.add_argument("--emit-replay-summary", action="store_true")
    parser.add_argument("--emit-report", action="store_true")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    events: List[Dict[str, Any]] = list(read_ndjson(args.events))

    st = initial_state(mode="REPLAY")
    for event in events:
        st = reduce_event(st, event)

    projection_snapshot = {
        "schema_version": st.schema_version,
        "run_id": st.run_id,
        "last_seq_processed": st.last_seq_processed,
        "viewer": st.viewer,
        "agents": st.agents,
        "jobs": st.jobs,
        "room_occupancy": st.room_occupancy,
        "alerts": st.alerts,
        "blocked_events": st.blocked_events,
        "warnings": st.warnings,
    }

    replay_summary = summary_to_dict(build_replay_summary(events))

    h_a = _hash_json_obj(projection_snapshot)
    st2 = initial_state(mode="REPLAY")
    for event in events:
        st2 = reduce_event(st2, event)
    projection_snapshot_b = {
        "schema_version": st2.schema_version,
        "run_id": st2.run_id,
        "last_seq_processed": st2.last_seq_processed,
        "viewer": st2.viewer,
        "agents": st2.agents,
        "jobs": st2.jobs,
        "room_occupancy": st2.room_occupancy,
        "alerts": st2.alerts,
        "blocked_events": st2.blocked_events,
        "warnings": st2.warnings,
    }
    h_b = _hash_json_obj(projection_snapshot_b)

    if args.emit_projection_snapshot:
        write_json(os.path.join(args.out, "projection_snapshot.json"), projection_snapshot)

    if args.emit_replay_summary:
        write_json(os.path.join(args.out, "expected_snapshot.json"), replay_summary)

    if args.emit_report:
        report = {
            "deterministic": h_a == h_b,
            "snapshot_hash_a": h_a,
            "snapshot_hash_b": h_b,
            "blocked_event_count": len(replay_summary.get("blocked_event_ids") or []),
        }
        write_json(os.path.join(args.out, "replay_report.json"), report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
