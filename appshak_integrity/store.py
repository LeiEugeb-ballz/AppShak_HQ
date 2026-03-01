from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

from .utils import atomic_write_text, to_timestamp_token


class IntegrityReportStore:
    def __init__(self, root: Path | str = "appshak_state/integrity") -> None:
        self.root = Path(root)

    def save(self, report: Mapping[str, Any], *, markdown: str | None = None) -> Dict[str, Path]:
        generated_at = str(report.get("generated_at", ""))
        token = to_timestamp_token(generated_at)
        report_dir = self.root / token
        report_dir = _next_unique_directory(report_dir)
        report_dir.mkdir(parents=True, exist_ok=False)

        report_path = report_dir / "report.json"
        atomic_write_text(report_path, json.dumps(dict(report), ensure_ascii=True, sort_keys=True, indent=2) + "\n")

        if markdown is not None:
            md_path = report_dir / "report.md"
            atomic_write_text(md_path, markdown.rstrip() + "\n")

        latest_payload = {
            "report_path": str(report_path),
            "generated_at": generated_at,
        }
        latest_path = self.root / "latest.json"
        atomic_write_text(latest_path, json.dumps(latest_payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n")

        return {
            "report_dir": report_dir,
            "report_path": report_path,
            "latest_path": latest_path,
        }

    def load_latest(self) -> Dict[str, Any]:
        latest_path = self.root / "latest.json"
        if not latest_path.exists():
            return {}
        try:
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(latest, Mapping):
            return {}
        report_path_raw = latest.get("report_path")
        if not isinstance(report_path_raw, str):
            return {}
        report_path = Path(report_path_raw)
        if not report_path.exists():
            return {}
        try:
            report_payload = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return report_payload if isinstance(report_payload, dict) else {}

    def load_history(self, *, limit: int = 20, cursor: str | None = None) -> Dict[str, Any]:
        directories = sorted(
            [path for path in self.root.iterdir() if path.is_dir()],
            key=lambda path: path.name,
            reverse=True,
        ) if self.root.exists() else []

        start = 0
        if isinstance(cursor, str) and cursor.strip():
            try:
                start = max(0, int(cursor))
            except Exception:
                start = 0
        page_size = max(1, min(200, int(limit)))
        selected = directories[start : start + page_size]

        items: List[Dict[str, Any]] = []
        for directory in selected:
            report_path = directory / "report.json"
            if not report_path.exists():
                continue
            try:
                payload = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict):
                items.append(payload)

        next_cursor = None
        if start + page_size < len(directories):
            next_cursor = str(start + page_size)

        return {
            "items": items,
            "cursor": str(start),
            "next_cursor": next_cursor,
            "total": len(directories),
        }


def render_markdown_report(report: Mapping[str, Any]) -> str:
    lines = [
        "# AppShak Integrity Report",
        "",
        f"- generated_at: {report.get('generated_at', 'n/a')}",
        f"- window: {report.get('window', 'n/a')}",
        f"- report_hash: {report.get('report_hash', 'n/a')}",
        "",
        "## Arbitration",
        f"- count: {report.get('arbitration', {}).get('count', 0)}",
        f"- efficiency_score: {report.get('arbitration', {}).get('arbitration_efficiency_score', 0.0)}",
        "",
        "## Trust",
        f"- volatility: {report.get('trust', {}).get('trust_volatility_score', 0.0)}",
        f"- drift: {report.get('trust', {}).get('governance_drift_indicator', 0.0)}",
        "",
        "## Propagation",
        f"- lessons_total: {report.get('propagation', {}).get('lessons_total', 0)}",
        f"- velocity: {report.get('propagation', {}).get('knowledge_propagation_velocity', 0.0)}",
        "",
    ]
    return "\n".join(lines)


def _next_unique_directory(path: Path) -> Path:
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.name}_v{index:02d}")
        if not candidate.exists():
            return candidate
        index += 1
