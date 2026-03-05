import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
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
    proc = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )
    line = proc.stdout.strip()
    if not line or "No tasks" in line:
        return None
    parts = [p.strip('"') for p in line.split(",")]
    if len(parts) < 5:
        return None
    mem_field = parts[4]
    match = re.search(r"([\d,]+)\s+K", mem_field)
    if not match:
        return None
    kb = int(match.group(1).replace(",", ""))
    return round(kb / 1024.0, 3)


def main() -> None:
    ws_proc = subprocess.Popen(
        [
            "python",
            str(WS_SCRIPT),
            "--url",
            "ws://127.0.0.1:8010/ws/events",
            "--output",
            str(WS_SUMMARY),
            "--duration",
            "220",
        ]
    )

    out_handle = STABILITY_OUT.open("w", encoding="utf-8")
    err_handle = STABILITY_ERR.open("w", encoding="utf-8")
    stability_proc = subprocess.Popen(
        ["python", "-m", "appshak_stability.run", "--duration-hours", "6"],
        stdout=out_handle,
        stderr=err_handle,
    )

    api_samples = []
    memory_samples = []

    try:
        while stability_proc.poll() is None:
            timestamp = utc_now()
            sample = {"timestamp": timestamp}
            try:
                health = fetch_json("http://127.0.0.1:8010/api/health")
                entities = fetch_json("http://127.0.0.1:8010/api/inspect/entities")
                sample.update(
                    {
                        "health_status": health.get("status"),
                        "last_snapshot_time": health.get("last_snapshot_time"),
                        "last_inspection_index_time": health.get("last_inspection_index_time"),
                        "last_integrity_report_time": health.get("last_integrity_report_time"),
                        "entities_count": int(entities.get("count", 0)),
                    }
                )
            except Exception as exc:
                sample["error"] = str(exc)
            api_samples.append(sample)

            memory_mb = sample_memory_mb(stability_proc.pid)
            memory_samples.append({"timestamp": timestamp, "working_set_mb": memory_mb})

            subprocess.run(["python", "-m", "appshak_integrity.run_report", "--window", "7d"], check=False)
            subprocess.run(["python", "-m", "appshak_inspection.run_index"], check=False)
            time.sleep(15)
    finally:
        code = stability_proc.wait(timeout=15)
        out_handle.close()
        err_handle.close()
        try:
            ws_proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            ws_proc.terminate()
            try:
                ws_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                ws_proc.kill()

        API_SAMPLES.write_text(json.dumps(api_samples, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
        MEMORY_SAMPLES.write_text(json.dumps(memory_samples, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
        SUMMARY.write_text(
            json.dumps(
                {
                    "stability_pid": stability_proc.pid,
                    "stability_exit": code,
                    "api_samples": len(api_samples),
                    "memory_samples": len(memory_samples),
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
