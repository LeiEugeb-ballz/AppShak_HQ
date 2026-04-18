from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class Phase4Snapshot:
    run_id: str
    timestamp: str
    agents: List[Dict[str, Any]]
    events: List[Dict[str, Any]]
    metrics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "agents": [dict(agent) for agent in self.agents],
            "events": [dict(event) for event in self.events],
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True)
class InspectionRecord:
    run_id: str
    timestamp: str
    anomalies: List[Dict[str, Any]]
    coverage: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "anomalies": [dict(anomaly) for anomaly in self.anomalies],
            "coverage": dict(self.coverage),
        }


@dataclass(frozen=True)
class IntegrityRecord:
    run_id: str
    timestamp: str
    consistency_score: float
    violations: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "consistency_score": float(self.consistency_score),
            "violations": [dict(violation) for violation in self.violations],
        }


@dataclass(frozen=True)
class ValidationResult:
    snapshot: Phase4Snapshot
    inspection: InspectionRecord
    integrity: IntegrityRecord

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot": self.snapshot.to_dict(),
            "inspection": self.inspection.to_dict(),
            "integrity": self.integrity.to_dict(),
        }
