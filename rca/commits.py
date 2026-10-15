"""Commit / deployment attribution (Phase 5, improvement I9).

When several services look suspicious, "what changed recently?" is the tie
breaker. A naive rule blames the *latest* deployment anywhere; the scenario
contains a decoy deployment on an unrelated service precisely to punish that.
Attribution here only considers deployments to services that are themselves
showing anomalies, then prefers the change closest to (and just before) the
anomaly onset.
"""

from __future__ import annotations

from dataclasses import dataclass

from ingestion.schema import NormalizedEvent, SourceType


@dataclass
class DeploymentMatch:
    service: str
    deployment_id: str | None
    commit_sha: str | None
    summary: str | None
    delta_seconds: float
    score: float


def attribute_deployment(
    service: str,
    onset,
    deployments: list[NormalizedEvent],
    window_seconds: float = 900.0,
) -> DeploymentMatch | None:
    """Best deployment-to-``service`` explanation for an anomaly ``onset``."""

    best: DeploymentMatch | None = None
    for event in deployments:
        if event.source_type != SourceType.DEPLOYMENT:
            continue
        if event.service_name != service:
            continue
        delta = (onset - event.event_time).total_seconds()
        # Only look at changes that landed before the symptom, within window.
        if delta < 0 or delta > window_seconds:
            continue
        score = 1.0 - (delta / window_seconds)
        if best is None or score > best.score:
            best = DeploymentMatch(
                service=service,
                deployment_id=event.deployment_id,
                commit_sha=event.attributes.get("commit_sha"),
                summary=event.message,
                delta_seconds=delta,
                score=score,
            )
    return best


def latest_deployment(
    onset, deployments: list[NormalizedEvent], window_seconds: float = 900.0
) -> DeploymentMatch | None:
    """Naive baseline: the *most recent* deployment on any service.

    This is the "we just shipped, so it must be the ship" heuristic. It looks
    symmetrically around the incident (a naive responder does not carefully
    require the change to precede the symptom), which is exactly what lets the
    decoy deployment trap it.
    """

    best: DeploymentMatch | None = None
    best_time = None
    for event in deployments:
        if event.source_type != SourceType.DEPLOYMENT:
            continue
        delta = (onset - event.event_time).total_seconds()
        if abs(delta) > window_seconds:
            continue
        if best_time is None or event.event_time > best_time:
            best_time = event.event_time
            best = DeploymentMatch(
                service=event.service_name or "unknown",
                deployment_id=event.deployment_id,
                commit_sha=event.attributes.get("commit_sha"),
                summary=event.message,
                delta_seconds=delta,
                score=1.0 - (abs(delta) / window_seconds),
            )
    return best


def latest_deployment_before(
    onset, deployments: list[NormalizedEvent], window_seconds: float = 900.0
) -> DeploymentMatch | None:
    """Most recent deployment strictly before ``onset`` (on any service)."""

    best: DeploymentMatch | None = None
    for event in deployments:
        if event.source_type != SourceType.DEPLOYMENT:
            continue
        delta = (onset - event.event_time).total_seconds()
        if delta < 0 or delta > window_seconds:
            continue
        score = 1.0 - (delta / window_seconds)
        if best is None or score > best.score:
            best = DeploymentMatch(
                service=event.service_name or "unknown",
                deployment_id=event.deployment_id,
                commit_sha=event.attributes.get("commit_sha"),
                summary=event.message,
                delta_seconds=delta,
                score=score,
            )
    return best
