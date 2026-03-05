import json
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

root = Path(__file__).resolve().parent
obs_port = 18010

proj_out = (root / 'projector.out.log').open('w', encoding='utf-8')
proj_err = (root / 'projector.err.log').open('w', encoding='utf-8')
obs_out = (root / 'observability.out.log').open('w', encoding='utf-8')
obs_err = (root / 'observability.err.log').open('w', encoding='utf-8')
procs = []


def fetch(url):
    with urlopen(url, timeout=2) as r:
        return r.status, json.loads(r.read().decode('utf-8'))

try:
    procs.append(subprocess.Popen(['python', '-m', 'appshak_projection.run_projector', '--mailstore-db', 'appshak_state/substrate/mailstore.db', '--view-path', 'appshak_state/projection/view.json', '--poll-interval', '1'], stdout=proj_out, stderr=proj_err))
    procs.append(subprocess.Popen(['python', '-m', 'appshak_observability.server', '--host', '127.0.0.1', '--port', str(obs_port), '--mailstore-db', 'appshak_state/substrate/mailstore.db', '--projection-view', 'appshak_state/projection/view.json', '--inspection-root', 'appshak_state/inspection', '--integrity-root', 'appshak_state/integrity', '--stability-root', 'appshak_state/stability'], stdout=obs_out, stderr=obs_err))

    ready = False
    for _ in range(40):
        time.sleep(1)
        try:
            status, payload = fetch(f'http://127.0.0.1:{obs_port}/api/health')
            if status == 200 and payload.get('status') == 'ok':
                ready = True
                break
        except Exception:
            pass

    if not ready:
        print('services_not_ready')
    else:
        r = subprocess.run(['python', str(root / 'operational_runner.py')], check=False)
        print(json.dumps({'ready': True, 'runner_exit': r.returncode}, sort_keys=True))
finally:
    for p in procs:
        if p.poll() is None:
            p.terminate()
    time.sleep(1)
    for p in procs:
        if p.poll() is None:
            p.kill()
    for h in [proj_out, proj_err, obs_out, obs_err]:
        h.close()
