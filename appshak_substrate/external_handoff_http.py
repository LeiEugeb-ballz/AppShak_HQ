"""Narrow loopback transport for an out-of-process external handoff worker.

Only pickup, lease renewal, and result return are exposed. Publishing and
task/route creation remain trusted backend operations, never HTTP operations.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from appshak_substrate.external_handoff import ExternalHandoffManager
from appshak_substrate.mailstore_sqlite import SQLiteMailStore


def create_handoff_server(handoffs: ExternalHandoffManager, port: int = 0) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            # Request headers may contain a credential. Never log them.
            return

        def do_POST(self) -> None:
            operations = {"/pickup", "/renew", "/result"}
            if self.path not in operations:
                self.send_error(404)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 4096:
                    raise ValueError("Invalid request size.")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("Request must be an object.")
                authorization = self.headers.get("Authorization", "")
                if not authorization.startswith("Bearer "):
                    raise PermissionError("Worker credential is required.")
                identity = {"target_id": body["target_id"], "worker_id": body["worker_id"],
                            "secret": authorization.removeprefix("Bearer ")}
                dispatch_id = body["dispatch_id"]
                if self.path == "/pickup":
                    result = handoffs.pickup(dispatch_id, **identity)
                elif self.path == "/renew":
                    result = {"renewed": handoffs.renew(dispatch_id, generation=body["generation"], **identity)}
                else:
                    result = handoffs.submit_result(dispatch_id, generation=body["generation"],
                                                    state=body["state"], sha256=body.get("sha256"), **identity)
                encoded = json.dumps(result).encode("utf-8")
                self.send_response(200)
            except (KeyError, TypeError, ValueError) as exc:
                encoded = json.dumps({"error": str(exc)}).encode("utf-8")
                self.send_response(400)
            except PermissionError:
                encoded = b'{"error":"unauthorized"}'
                self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the S2D worker boundary on loopback only.")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--port", type=int, default=8011)
    args = parser.parse_args()
    if not Path(args.db_path).is_file():
        parser.error("Existing canonical mailstore required; it will not be initialized implicitly.")
    handoffs = ExternalHandoffManager(SQLiteMailStore(args.db_path))
    with handoffs.store._connection() as conn:
        active = [row[0] for row in conn.execute("SELECT dispatch_id FROM baton_dispatches "
            "WHERE status IN ('HANDOFF_DISPATCHED', 'EXTERNAL_PICKUP_ACKNOWLEDGED')")]
    for dispatch_id in active:
        handoffs.reconcile(dispatch_id)
    server = create_handoff_server(handoffs, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
