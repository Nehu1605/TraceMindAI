"""Propagation-aware root-cause analysis (Phase 5)."""

from .commits import (
    DeploymentMatch,
    attribute_deployment,
    latest_deployment,
    latest_deployment_before,
)
from .engine import RCAEngine, RCAReport
from .ranking import Candidate, rank_candidates, top_candidate
from .topology import build_service_graph, fallback_graph, path_confidence

__all__ = [
    "Candidate",
    "DeploymentMatch",
    "RCAEngine",
    "RCAReport",
    "attribute_deployment",
    "build_service_graph",
    "fallback_graph",
    "latest_deployment",
    "latest_deployment_before",
    "path_confidence",
    "rank_candidates",
    "top_candidate",
]
