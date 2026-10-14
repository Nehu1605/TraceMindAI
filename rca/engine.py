"""The RCA engine (Phase 5).

Ties detection, topology, propagation ranking, commit attribution and the
baselines together into one ``RCAReport``:

* every ranked candidate is explainable (component scores + evidence ids),
* the top-3 are returned for reviewer context,
* a confidence label and an explicit **abstain** state avoid confident guesses,
* the naive baselines are computed on the same input for later comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from common.config import Settings, get_settings
from detection.detector import AnomalyDetector
from ingestion.schema import NormalizedEvent, Severity, SourceType

from . import baselines
from .ranking import Candidate, rank_candidates
from .topology import build_service_graph

_ERROR_SEVERITIES = {Severity.ERROR, Severity.FATAL}


@dataclass
class RCAReport:
    candidates: list[Candidate] = field(default_factory=list)
    baselines: dict[str, list[str]] = field(default_factory=dict)
    anomalous_services: list[str] = field(default_factory=list)

    @property
    def top_cause(self) -> Candidate | None:
        return self.candidates[0] if self.candidates else None

    @property
    def abstained(self) -> bool:
        top = self.top_cause
        return top is None or top.confidence == "abstain"

    def summary(self) -> str:
        top = self.top_cause
        if top is None:
            return "No anomalies detected; nothing to explain."
        if self.abstained:
            return "Insufficient evidence to name a root cause; escalating for review."
        return (
            f"Most likely root cause: {top.service} "
            f"(confidence {top.confidence}, score {top.score:.2f}). {top.rationale}"
        )

    def to_dict(self) -> dict:
        return {
            "anomalous_services": self.anomalous_services,
            "abstained": self.abstained,
            "summary": self.summary(),
            "top_k": [c.to_dict() for c in self.candidates],
            "baselines": self.baselines,
        }


class RCAEngine:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.detector = AnomalyDetector(self.settings)

    def analyze(self, events: list[NormalizedEvent]) -> RCAReport:
        detection = self.detector.detect(events)
        if not detection.anomalies:
            return RCAReport()

        service_graph = build_service_graph(events)
        deployments = [e for e in events if e.source_type == SourceType.DEPLOYMENT]
        error_log_counts: dict[str, int] = {}
        for event in events:
            if (
                event.source_type == SourceType.LOG
                and event.severity in _ERROR_SEVERITIES
                and event.service_name
            ):
                error_log_counts[event.service_name] = (
                    error_log_counts.get(event.service_name, 0) + 1
                )

        candidates = rank_candidates(
            service_graph, detection.anomalies, deployments, error_log_counts, self.settings
        )

        baseline_ranks = {
            "B1_latest_anomaly": baselines.b1_latest_anomaly(detection.anomalies, deployments),
            "B2_max_magnitude": baselines.b2_max_magnitude(detection.anomalies, deployments),
            "B3_log_volume": baselines.b3_log_volume(
                detection.anomalies, deployments, error_log_counts
            ),
            "B4_latest_deploy": baselines.b4_latest_deploy(detection.anomalies, deployments),
        }

        return RCAReport(
            candidates=candidates,
            baselines=baseline_ranks,
            anomalous_services=sorted({a.service for a in detection.anomalies}),
        )
