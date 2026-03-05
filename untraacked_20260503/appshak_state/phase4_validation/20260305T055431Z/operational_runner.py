import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
PORT = 18010

WS_SCRIPT = ROOT / "ws_monitor.py"
WS_SUMMARY = ROOT / "ws_summary.json"
API_SAMPLES = ROOT / "api_samples.json"
MEMORY_SAMPLES = ROOT / "memory_samples.json"
SUMMARY = ROOT / "runner_summary.json"
STABILITY_OUT = ROOT / "stability.out.log"
STABILITY_ERR = ROOT / "stability.err.log"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_json(url: str):
    with urlopen(url, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def sample_memory_mb(pid: int):
    proc = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True, check=False)
    line = proc.stdout.strip()
    if not line or "No tasks" in line:
        return None
    parts = [p.strip('"') for p in line.split(",")]
    if len(parts) < 5:
        return None
    m = re.search(r"([\d,]+)\s+K", parts[4])
    if not m:
        return None
    return round(int(m.group(1).replace(",", "")) / 1024.0, 3)


if __name__ == "__main__":
    ws_proc = subprocess.Popen([
        "python", str(WS_SCRIPT), "--url", f"ws://127.0.0.1:{PORT}/ws/events", "--output", str(WS_SUMMARY), "--duration", "220"
    ])
    out_h = STABILITY_OUT.open("w", encoding="utf-8")
    err_h = STABILITY_ERR.open("w", encoding="utf-8")
    stability = subprocess.Popen(["python", "-m", "appshak_stability.run", "--duration-hours", "6"], stdout=out_h, stderr=err_h)

    api = []
    mem = []
    try:
        while stability.poll() is None:
            ts = utc_now()
            row = {"timestamp": ts}
            try:
                h = fetch_json(f"http://127.0.0.1:{PORT}/api/health")
                e = fetch_json(f"http://127.0.0.1:{PORT}/api/inspect/entities")
                row.update({
                    "health_status": h.get("status"),
                    "last_snapshot_time": h.get("last_snapshot_time"),
                    "last_inspection_index_time": h.get("last_inspection_index_time"),
                    "last_integrity_report_time": h.get("last_integrity_report_time"),
                    "entities_count": int(e.get("count", 0)),
                })
            except Exception as exc:
                row["error"] = str(exc)
            api.append(row)
            mem.append({"timestamp": ts, "working_set_mb": sample_memory_mb(stability.pid)})
            subprocess.run(["python", "-m", "appshak_integrity.run_report", "--window", "7d"], check=False)
            subprocess.run(["python", "-m", "appshak_inspection.run_index"], check=False)
            time.sleep(15)
    finally:
        code = stability.wait(timeout=15)
        out_h.close()
        err_h.close()
        try:
            ws_proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            ws_proc.terminate()
            try:
                ws_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                ws_proc.kill()
        API_SAMPLES.write_text(json.dumps(api, ensure_ascii=True, sort_keys=True, indent=2), encoding="utf-8")
        MEMORY_SAMPLES.write_text(json.dumps(mem, ensure_ascii=True, sort_keys=True, indent=2), encoding="utf-8")
        SUMMARY.write_text(json.dumps({"stability_pid": stability.pid, "stability_exit": code, "api_samples": len(api), "memory_samples": len(mem)}, ensure_ascii=True, sort_keys=True, indent=2), encoding="utf-8")
