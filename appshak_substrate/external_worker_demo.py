"""Separate-process local worker for the S2D transport contract and tests.

This adapter has no provider integration. The credential arrives only through
the process environment; it is never printed or persisted in plaintext.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def post(endpoint: str, operation: str, body: dict, secret: str) -> dict:
    request = Request(endpoint + operation, data=json.dumps(body).encode("utf-8"),
                      headers={"Content-Type": "application/json", "Authorization": f"Bearer {secret}"},
                      method="POST")
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one local external handoff pickup.")
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--dispatch-id", required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--content", default="")
    parser.add_argument("--fail", action="store_true")
    parser.add_argument("--stop-after-pickup", action="store_true")
    parser.add_argument("--stop-after-write", action="store_true")
    args = parser.parse_args()
    parsed = urlparse(args.endpoint)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
        parser.error("The handoff endpoint must be a loopback HTTP address.")
    secret = os.environ.get("APPSHAK_HANDOFF_SECRET")
    if not secret:
        parser.error("APPSHAK_HANDOFF_SECRET is required in the process environment.")
    identity = {"dispatch_id": args.dispatch_id, "target_id": args.target_id,
                "worker_id": args.worker_id}
    handoff = post(args.endpoint, "/pickup", identity, secret)
    if args.stop_after_pickup:
        print(json.dumps({"dispatch_id": args.dispatch_id, "status": handoff["status"]}))
        return 0
    generation = handoff["pickup_generation"]
    if args.fail:
        result = post(args.endpoint, "/result", {**identity, "generation": generation,
                                                  "state": "FAILED"}, secret)
    else:
        destination = Path(handoff["result_reference"])
        content = args.content.encode("utf-8")
        try:
            with destination.open("xb") as stream:
                stream.write(content)
        except FileExistsError:
            if destination.read_bytes() != content:
                raise ValueError("An existing external result has different bytes.")
        if args.stop_after_write:
            print(json.dumps({"dispatch_id": args.dispatch_id, "status": "EFFECT_UNCONFIRMED"}))
            return 0
        result = post(args.endpoint, "/result", {**identity, "generation": generation,
                      "state": "SUCCEEDED", "sha256": hashlib.sha256(content).hexdigest()}, secret)
    print(json.dumps({"dispatch_id": args.dispatch_id, "status": result["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
