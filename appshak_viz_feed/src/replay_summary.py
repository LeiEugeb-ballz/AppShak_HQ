from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple

from .normalize import norm_outcome


@dataclass
class ReplaySummary:
    source_mode: str = "derived_from_mirrored_feed"
    run_ids: List[str] = None
    event_count: int = 0
    seq_range: Dict[str, int] = None
    by_type: Dict[str, int] = None
    by_phase: Dict[str, int] = None
    blocked_event_ids: List[str] = None
    job_spans: Dict[str, Any] = None
    overlap_pairs: List[Dict[str, str]] = None


def build_replay_summary(events: List[Dict[str, Any]]) -> ReplaySummary:
    run_ids: List[str] = []
    by_type: Dict[str, int] = {}
    by_phase: Dict[str, int] = {}
    blocked_ids: List[str] = []
    seqs: List[int] = []
    job_events: Dict[str, List[Dict[str, Any]]] = {}

    for event in events:
        run_id = event.get("run_id")
        if isinstance(run_id, str) and run_id not in run_ids:
            run_ids.append(run_id)

        event_type = str(event.get("type") or "")
        by_type[event_type] = by_type.get(event_type, 0) + 1

        payload = event.get("payload") or {}
        phase = payload.get("phase")
        if isinstance(phase, str) and phase.strip():
            normalized_phase = phase.strip().upper()
            by_phase[normalized_phase] = by_phase.get(normalized_phase, 0) + 1

        seq = event.get("seq")
        if isinstance(seq, int):
            seqs.append(seq)

        job_id = event.get("job_id")
        if isinstance(job_id, str) and job_id.strip():
            job_events.setdefault(job_id, []).append(event)

        outcome = norm_outcome(payload.get("outcome")).value
        if outcome in {"BLOCKED", "DENIED"}:
            event_id = event.get("event_id")
            if isinstance(event_id, str):
                blocked_ids.append(event_id)

    job_spans: Dict[str, Any] = {}
    spans: Dict[str, Tuple[int, int]] = {}
    for job_id, job_event_list in job_events.items():
        ordered = sorted(job_event_list, key=lambda item: int(item.get("seq", 0)))
        seq_start = int(ordered[0].get("seq", 0))
        seq_end = int(ordered[-1].get("seq", 0))
        spans[job_id] = (seq_start, seq_end)

        phases: List[str] = []
        correlation_id = None
        for event in ordered:
            if not correlation_id and isinstance(event.get("correlation_id"), str):
                correlation_id = event["correlation_id"]
            phase = (event.get("payload") or {}).get("phase")
            if isinstance(phase, str) and phase.strip():
                phases.append(phase.strip().upper())

        job_spans[job_id] = {
            "job_id": job_id,
            "correlation_id": correlation_id,
            "event_count": len(ordered),
            "seq_start": seq_start,
            "seq_end": seq_end,
            "phases": sorted(set(phases)),
        }

    job_ids = sorted(spans.keys())
    overlap_pairs: List[Dict[str, str]] = []
    for i in range(len(job_ids)):
        for j in range(i + 1, len(job_ids)):
            left, right = job_ids[i], job_ids[j]
            left_start, left_end = spans[left]
            right_start, right_end = spans[right]
            if not (left_end < right_start or right_end < left_start):
                overlap_pairs.append({"left": left, "right": right})

    seq_range = {"min": min(seqs) if seqs else 0, "max": max(seqs) if seqs else 0}
    return ReplaySummary(
        run_ids=run_ids,
        event_count=len(events),
        seq_range=seq_range,
        by_type=dict(sorted(by_type.items())),
        by_phase=dict(sorted(by_phase.items())),
        blocked_event_ids=blocked_ids,
        job_spans=dict(sorted(job_spans.items())),
        overlap_pairs=overlap_pairs,
    )


def to_dict(summary: ReplaySummary) -> Dict[str, Any]:
    return asdict(summary)
