"""Unit tests for the ranking engine (I2/I8/I12)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import networkx as nx

from common.config import Settings
from detection.detector import Anomaly
from ingestion.schema import NormalizedEvent, SourceType
from rca.ranking import Candidate, rank_candidates

BASE = datetime(2026, 10, 11, 10, 0, 0, tzinfo=timezone.utc)


def anomaly(service: str, metric: str, mag: float, offset: float) -> Anomaly:
    return Anomaly(
        service=service,
        metric=metric,
        direction="up",
        magnitude=mag,
        onset_time=BASE + timedelta(seconds=offset),
        end_time=BASE + timedelta(seconds=offset + 5),
        observed_peak=mag,
        baseline_median=0.0,
        evidence_ids=[f"e-{service}-{metric}"],
    )


def test_shared_dependency_rises_via_propagation():
    # payment is called by both order and api-gateway -> high propagation
    anomalies = [
        anomaly("payment-service", "db_connections_in_use", 10.0, 2.0),
        anomaly("order-service", "error_rate", 5.0, 0.0),
        anomaly("api-gateway", "error_rate", 5.0, 0.0),
    ]
    graph = nx.DiGraph()
    graph.add_edges_from(
        [("api-gateway", "order-service"), ("order-service", "payment-service")]
    )
    deployments: list[NormalizedEvent] = []
    error_counts = {"payment-service": 20, "order-service": 5, "api-gateway": 5}

    candidates = rank_candidates(
        graph, anomalies, deployments, error_counts, Settings()
    )

    assert candidates[0].service == "payment-service"
    assert candidates[0].components["propagation"] > candidates[1].components["propagation"]


def test_commit_attribution_boosts_the_true_cause():
    anomalies = [anomaly("payment-service", "db_connections_in_use", 10.0, 2.0)]
    graph = nx.DiGraph()
    graph.add_edges_from(
        [("api-gateway", "order-service"), ("order-service", "payment-service")]
    )
    deployments = [
        NormalizedEvent(
            event_id="d-real",
            event_time=BASE + timedelta(seconds=1),
            ingestion_time=BASE + timedelta(seconds=1),
            source_type=SourceType.DEPLOYMENT,
            event_type="DEPLOYMENT",
            service_name="payment-service",
            attributes={"commit_sha": "c0ffee"},
        )
    ]
    error_counts = {"payment-service": 5}

    candidates = rank_candidates(
        graph, anomalies, deployments, error_counts, Settings()
    )

    assert candidates[0].service == "payment-service"
    assert candidates[0].deployment is not None
    assert candidates[0].deployment.commit_sha == "c0ffee"


def test_abstain_when_no_candidate_clears_the_bar():
    anomalies = [anomaly("payment-service", "db_connections_in_use", 0.5, 2.0)]
    graph = nx.DiGraph()
    graph.add_edges_from(
        [("api-gateway", "order-service"), ("order-service", "payment-service")]
    )
    deployments: list[NormalizedEvent] = []
    error_counts = {}

    candidates = rank_candidates(
        graph, anomalies, deployments, error_counts, Settings(rca_abstain_threshold=0.5)
    )

    assert candidates[0].confidence == "abstain"


def test_confidence_labels_from_margins():
    anomalies = [anomaly("payment-service", "db_connections_in_use", 10.0, 2.0)]
    graph = nx.DiGraph()
    graph.add_edges_from(
        [("api-gateway", "order-service"), ("order-service", "payment-service")]
    )
    deployments: list[NormalizedEvent] = []
    error_counts = {"payment-service": 5}

    candidates = rank_candidates(
        graph, anomalies, deployments, error_counts, Settings()
    )

    assert candidates[0].confidence in {"high", "medium", "low"}


def test_top_k_returns_three_candidates():
    anomalies = [
        anomaly("a", "x", 1.0, 0.0),
        anomaly("b", "y", 1.0, 0.0),
        anomaly("c", "z", 1.0, 0.0),
    ]
    graph = nx.DiGraph()
    graph.add_edges_from([("a", "b"), ("b", "c")])
    deployments: list[NormalizedEvent] = []
    error_counts = {"a": 1, "b": 1, "c": 1}

    candidates = rank_candidates(graph, anomalies, deployments, error_counts, Settings())

    assert len(candidates) == 3