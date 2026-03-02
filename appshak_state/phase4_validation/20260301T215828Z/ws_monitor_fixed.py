import asyncio, json, pathlib, time
import websockets

out_path = pathlib.Path('appshak_state/phase4_validation/20260301T215828Z/ws_summary.json')
max_seconds = 240
seen = set()
by_channel = {}
duplicates = 0
messages = 0
start = time.time()

async def run():
    global duplicates, messages
    uri = 'ws://127.0.0.1:8010/ws/events'
    while time.time() - start < max_seconds:
        try:
            async with websockets.connect(uri, open_timeout=5, ping_interval=20, ping_timeout=20) as ws:
                while time.time() - start < max_seconds:
                    timeout = max(0.2, min(2.0, max_seconds - (time.time() - start)))
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    except asyncio.TimeoutError:
                        continue
                    messages += 1
                    payload = json.loads(msg)
                    ch = str(payload.get('channel','unknown'))
                    by_channel[ch] = by_channel.get(ch, 0) + 1
                    key = json.dumps(payload, sort_keys=True, separators=(',', ':'))
                    if key in seen:
                        duplicates += 1
                    else:
                        seen.add(key)
        except Exception:
            await asyncio.sleep(0.5)

    out_path.write_text(json.dumps({'message_count': messages, 'unique_message_count': len(seen), 'duplicate_message_count': duplicates, 'by_channel': by_channel}, ensure_ascii=True, sort_keys=True, indent=2) + '\n', encoding='utf-8')

asyncio.run(run())