import argparse
import asyncio
import json
from collections import Counter

import websockets


def canonical(payload):
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


async def run(url: str, output: str, duration: float) -> None:
    counts = Counter()
    messages = []
    start = asyncio.get_running_loop().time()
    try:
        async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
            while True:
                if asyncio.get_running_loop().time() - start >= duration:
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                payload = json.loads(raw)
                counts[str(payload.get("channel", "unknown"))] += 1
                messages.append(canonical(payload))
    except Exception as exc:
        counts["ws_error"] += 1
        messages.append(canonical({"error": str(exc)}))

    unique = len(set(messages))
    with open(output, "w", encoding="utf-8") as h:
        json.dump({
            "message_count": len(messages),
            "unique_message_count": unique,
            "duplicate_message_count": len(messages) - unique,
            "by_channel": dict(sorted(counts.items())),
        }, h, ensure_ascii=True, indent=2, sort_keys=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--duration", type=float, default=220.0)
    a = p.parse_args()
    asyncio.run(run(a.url, a.output, a.duration))
