from __future__ import annotations

import argparse
import time
from pathlib import Path

from appshak_substrate.mailstore_sqlite import SQLiteMailStore

from .projector import ProjectionProjector
from .view_store import ProjectionViewStore


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AppShak projection materializer.")
    parser.add_argument("--mailstore-db", type=str, default="appshak_state/substrate/mailstore.db")
    parser.add_argument("--view-path", type=str, default="appshak_state/projection/view.json")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--audit-fetch-limit", type=int, default=100_000)
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    mail_store = SQLiteMailStore(Path(args.mailstore_db))
    view_store = ProjectionViewStore(Path(args.view_path))
    projector = ProjectionProjector(
        mail_store=mail_store,
        view_store=view_store,
        audit_fetch_limit=max(1, int(args.audit_fetch_limit)),
    )

    if args.once:
        projector.project_once()
        return

    poll_interval = max(0.1, float(args.poll_interval))
    while True:
        projector.project_once()
        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
