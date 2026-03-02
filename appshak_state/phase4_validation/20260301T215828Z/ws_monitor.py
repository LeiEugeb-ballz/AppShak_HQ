import asyncio, json, pathlib, signal, sys
import websockets

out_path = pathlib.Path(sys.argv[1])
seen = set()
by_channel = {}
duplicate_count = 0
message_count = 0
stop = False

def _stop(*_args):
    global stop
    stop = True

signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)

async def run():
    global duplicate_count, message_count
    uri = 'ws://127.0.0.1:8010/ws/events'
    while not stop:
        try:
            async with websockets.connect(uri, open_timeout=5, ping_interval=20, ping_timeout=20) as ws:
                while not stop:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=2)
                    except asyncio.TimeoutError:
                        continue
                    message_count += 1
                    payload = json.loads(msg)
                    ch = str(payload.get('channel','unknown'))
                    by_channel[ch] = by_channel.get(ch, 0) + 1
                    key = json.dumps(payload, sort_keys=True, separators=(',', ':'))
                    if key in seen:
                        duplicate_count += 1
                    else:
                        seen.add(key)
        except Exception:
            await asyncio.sleep(0.5)

    result = {
        'message_count': message_count,
        'unique_message_count': len(seen),
        'duplicate_message_count': duplicate_count,
        'by_channel': by_channel,
    }
    out_path.write_text(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2) + '\n', encoding='utf-8')

asyncio.run(run())