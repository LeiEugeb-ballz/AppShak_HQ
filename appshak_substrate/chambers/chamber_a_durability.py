from __future__ import annotations

import argparse
import time
from pathlib import Path

from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.types import SubstrateEvent


def run_chamber(*, db_path: Path, event_count: int = 100) -> int:
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = SQLiteMailStore(db_path, lease_seconds=0.5, poll_interval=0.05)

    for idx in range(event_count):
        store.append_event(
            SubstrateEvent(
                type="CHAMBER_A_EVENT",
                origin_id="chamber_a",
                target_agent="recon",
                payload={"index": idx, "target_agent": "recon"},
            )
        )

    acked_ids: list[int] = []

    # Simulated crash: consumer claims one event and exits before ack.
    for idx in range(60):
        event = store.claim_next_event("consumer_a", timeout=1.0, target_agent="recon", include_unrouted=False)
        if event is None or event.event_id is None:
            break
        if idx == 59:
            # Crash point: do not ack this lease.
            break
        store.ack_event(event.event_id, consumer_id="consumer_a")
        acked_ids.append(event.event_id)

    time.sleep(0.7)  # wait until lease expires

    while True:
        event = store.claim_next_event("consumer_b", timeout=0.2, target_agent="recon", include_unrouted=False)
        if event is None:
            break
        if event.event_id is None:
            continue
        store.ack_event(event.event_id, consumer_id="consumer_b")
        acked_ids.append(event.event_id)

    counts = store.status_counts()
    done_count = counts.get("DONE", 0)
    unique_done = len(set(acked_ids))
    duplicate_done = len(acked_ids) - unique_done
    passed = done_count == event_count and unique_done == event_count and duplicate_done == 0

    print(f"Chamber A: {'PASS' if passed else 'FAIL'}")
    print(f"db_path={db_path}")
    print(f"done_count={done_count} expected={event_count}")
    print(f"unique_done={unique_done} duplicate_done={duplicate_done}")
    print(f"status_counts={counts}")
    return 0 if passed else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Chamber A durability validation.")
    parser.add_argument("--db-path", type=str, default="appshak_state/substrate/chamber_a.db")
    parser.add_argument("--events", type=int, default=100)
    args = parser.parse_args()
    raise SystemExit(run_chamber(db_path=Path(args.db_path), event_count=max(1, int(args.events))))


if __name__ == "__main__":
    main()
