import csv
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path('appshak_state/phase4_validation/20260301T215828Z')


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_memory_mb(pid: int):
    try:
        raw = subprocess.check_output(['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'], text=True)
    except Exception:
        return None
    line = raw.strip()
    if not line or line.startswith('INFO:'):
        return None
    row = next(csv.reader([line]))
    if len(row) < 5:
        return None
    mem_field = row[4]
    digits = ''.join(re.findall(r'\d', mem_field))
    if not digits:
        return None
    kb = float(digits)
    return round(kb / 1024.0, 3)


def get_json(url: str):
    with urlopen(url, timeout=5) as r:
        return json.loads(r.read().decode('utf-8'))

ws_proc = subprocess.Popen(['python', str(ROOT / 'ws_monitor_fixed.py')], stdout=open(ROOT / 'ws_fixed.out.log', 'w', encoding='utf-8'), stderr=open(ROOT / 'ws_fixed.err.log', 'w', encoding='utf-8'))

st_proc = subprocess.Popen(['python', '-m', 'appshak_stability.run', '--duration-hours', '6'], stdout=open(ROOT / 'stability_v2.out.log', 'w', encoding='utf-8'), stderr=open(ROOT / 'stability_v2.err.log', 'w', encoding='utf-8'))

memory_samples = []
api_samples = []
while st_proc.poll() is None:
    mem_mb = get_memory_mb(st_proc.pid)
    if mem_mb is not None:
        memory_samples.append({'timestamp': now_iso(), 'working_set_mb': mem_mb})

    sample = {'timestamp': now_iso(), 'health_status': 'error', 'entities_count': -1, 'last_snapshot_time': None, 'last_inspection_index_time': None, 'last_integrity_report_time': None}
    try:
        health = get_json('http://127.0.0.1:8010/api/health')
        entities = get_json('http://127.0.0.1:8010/api/inspect/entities')
        sample.update({'health_status': 'ok', 'entities_count': int(entities.get('count', -1)), 'last_snapshot_time': health.get('last_snapshot_time'), 'last_inspection_index_time': health.get('last_inspection_index_time'), 'last_integrity_report_time': health.get('last_integrity_report_time')})
    except Exception:
        pass
    api_samples.append(sample)

    subprocess.run(['python', '-m', 'appshak_integrity.run_report', '--window', '7d'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['python', '-m', 'appshak_inspection.run_index'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(15)

exit_code = st_proc.poll()
ws_proc.wait(timeout=300)

(ROOT / 'memory_samples_v2.json').write_text(json.dumps(memory_samples, ensure_ascii=True, sort_keys=True, indent=2) + '\n', encoding='utf-8')
(ROOT / 'api_samples_v2.json').write_text(json.dumps(api_samples, ensure_ascii=True, sort_keys=True, indent=2) + '\n', encoding='utf-8')
(ROOT / 'runner_summary_v2.json').write_text(json.dumps({'stability_pid': st_proc.pid, 'stability_exit': exit_code, 'memory_samples': len(memory_samples), 'api_samples': len(api_samples)}, ensure_ascii=True, sort_keys=True, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'stability_pid': st_proc.pid, 'stability_exit': exit_code, 'memory_samples': len(memory_samples), 'api_samples': len(api_samples)}, ensure_ascii=True, sort_keys=True))