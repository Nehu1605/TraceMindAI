"""Propagation-aware root-cause ranking (Phase 5, improvements I2/I8/I12).

Symptoms are ranked, not just listed. A candidate service is judged on four
signals:

1. **magnitude** - how strong its own anomalies are;
2. **propagation** - how many *other* anomalous services sit upstream of it in
   the call graph (a dependency shared by failing callers is a strong root);
3. **commit** - whether a deployment to that service landed just before onset;
4. **logs** - the volume of errors attributed to it.

The combined score is deliberately explainable: every candidate carries its
component scores, the evidence ids behind them and a plain-English rationale.
Confidence is derived from the margin between the top two candidates, and the
engine can **abstain** when no candidate clears the bar (I12).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import networkx as nx

from common.config import Settings, get_settings
from ingestion.schema import NormalizedEvent

from .commits import DeploymentMatch, attribute_deployment
from .topology import path_confidence

WEIGHTS = {"magnitude": 0.35, "propagation": 0.30, "commit": 0.25, "logs": 0.10}


@dataclass
class Candidate:
    service: str
    score: float
    components: dict[str, float]
    evidence_ids: list[str] = field(default_factory=list)
    rationale: str = ""
    confidence: str = "low"
    deployment: DeploymentMatch | None = None

    def to_dict(self) -> dict:
        return {
            "service": self.service,
            "score": round(self.score, 4),
            "confidence": self.confidence,
            "components": {k: round(v, 4) for k, v in self.components.items()},
            "evidence_ids": self.evidence_ids,
            "rationale": self.rationale,
            "deployment": None
            if self.deployment is None
            else {
                "deployment_id": self.deployment.deployment_id,
                "commit_sha": self.deployment.commit_sha,
                "summary": self.deployment.summary,
                "score": round(self.deployment.score, 4),
            },
        }


def _normalize(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    peak = max(values.values())
    if peak <= 0:
        return {key: 0.0 for key in values}
    return {key: value / peak for key, value in values.items()}


def _max_magnitude(anomalies) -> dict[str, float]:
    out: dict[str, float] = {}
    for anomaly in anomalies:
        out[anomaly.service] = max(out.get(anomaly.service, 0.0), anomaly.magnitude)
    return out


def rank_candidates(
    service_graph: nx.DiGraph,
    anomalies: list,
    deployments: list[NormalizedEvent],
    error_log_counts: dict[str, int],
    settings: Settings | None = None,
) -> list[Candidate]:
    settings = settings or get_settings()
    services = sorted({a.service for a in anomalies})
    if not services:
        return []

    onsets: dict[str, list[datetime]] = {}
    for anomaly in anomalies:
        onsets.setdefault(anomaly.service, []).append(anomaly.onset_time)

    raw_magnitude = _max_magnitude(anomalies)
    magnitude = _normalize(raw_magnitude)

    raw_propagation: dict[str, float] = {}
    for candidate in services:
        raw_propagation[candidate] = sum(
            path_confidence(service_graph, other, candidate)
            for other in services
            if other != candidate
        )
    propagation = _normalize(raw_propagation)

    logs = _normalize({s: float(error_log_counts.get(s, 0)) for s in services})

    evidence_by_service: dict[str, list[str]] = {}
    for anomaly in anomalies:
        evidence_by_service.setdefault(anomaly.service, []).extend(anomaly.evidence_ids)

    candidates: list[Candidate] = []
    for service in services:
        # A service is "explained" by a deploy if *any* of its anomaly onsets is
        # preceded by that deploy. Bucketing can push a derived error onset a
        # few seconds before the change, so we consider every onset.
        match = None
        for onset in onsets.get(service, []):
            candidate_match = attribute_deployment(
                service, onset, deployments, window_seconds=settings.commit_window_seconds
            )
            if candidate_match is not None and (
                match is None or candidate_match.score > match.score
            ):
                match = candidate_match
        commit_score = match.score if match else 0.0
        components = {
            "magnitude": magnitude.get(service, 0.0),
            "propagation": propagation.get(service, 0.0),
            "commit": commit_score,
            "logs": logs.get(service, 0.0),
        }
        score = sum(WEIGHTS[key] * components[key] for key in WEIGHTS)
        candidates.append(
            Candidate(
                service=service,
                score=score,
                components=components,
                evidence_ids=list(dict.fromkeys(evidence_by_service.get(service, [])))[:10],
                deployment=match,
                rationale=_rationale(service, components, match),
            )
        )

    candidates.sort(key=lambda c: c.score, reverse=True)
    _assign_confidence(candidates, settings)
    return candidates


def _assign_confidence(candidates: list[Candidate], settings: Settings) -> None:
    if not candidates:
        return
    top = candidates[0]
    margin = top.score - (candidates[1].score if len(candidates) > 1 else 0.0)
    if top.score < settings.rca_abstain_threshold:
        top.confidence = "abstain"
    elif margin >= settings.rca_high_margin:
        top.confidence = "high"
    elif margin >= settings.rca_medium_margin:
        top.confidence = "medium"
    else:
        top.confidence = "low"
    for candidate in candidates[1:]:
        candidate.confidence = "low"


def _rationale(
    service: str, components: dict[str, float], match: DeploymentMatch | None
) -> str:
    parts: list[str] = []
    if components["propagation"] > 0:
        parts.append(
            f"{service} is a shared dependency of other degraded services "
            f"(propagation {components['propagation']:.2f})"
        )
    if components["magnitude"] > 0:
        parts.append(f"it has the strongest local anomalies (magnitude {components['magnitude']:.2f})")
    if match is not None:
        parts.append(
            f"commit {match.commit_sha} deployed {match.delta_seconds:.0f}s before onset"
        )
    if components["logs"] > 0:
        parts.append(f"error logs cluster on it (relative {components['logs']:.2f})")
    return "; ".join(parts) if parts else "no strong evidence"


def top_candidate(candidates: list[Candidate]) -> Candidate | None:
    return candidates[0] if candidates else None
