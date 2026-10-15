"""Unit tests for the RCA topology (I2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ingestion.schema import NormalizedEvent, SourceType
from rca.topology import build_service_graph, fallback_graph, path_confidence

BASE = datetime(2026, 10, 11, 10, 0, 0, tzinfo=timezone.utc)


def span(service: str, span_id: str, parent: str | None, offset: float = 0.0) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=f"s-{span_id}",
        event_time=BASE + timedelta(seconds=offset),
        ingestion_time=BASE + timedelta(seconds=offset),
        source_type=SourceType.TRACE,
        event_type="SPAN",
        service_name=service,
        span_id=span_id,
        parent_span_id=parent,
    )


def test_builds_cross_service_edges_from_spans():
    events = [
        span("api-gateway", "a", None),
        span("order-service", "b", "a"),
        span("payment-service", "c", "b"),
    ]

    graph = build_service_graph(events)

    assert graph.has_edge("api-gateway", "order-service")
    assert graph.has_edge("order-service", "payment-service")
    assert not graph.has_edge("payment-service", "order-service")


def test_falls_back_when_no_cross_service_spans():
    events = [span("api-gateway", "a", None), span("api-gateway", "b", "a")]

    graph = build_service_graph(events)

    assert graph.has_edge("order-service", "payment-service")


def test_fallback_graph_matches_known_topology():
    graph = fallback_graph()
    assert path_confidence(graph, "api-gateway", "payment-service") > 0
    assert path_confidence(graph, "payment-service", "api-gateway") == 0.0


def test_path_confidence_decays_with_distance():
    graph = fallback_graph()
    direct = path_confidence(graph, "order-service", "payment-service")
    indirect = path_confidence(graph, "api-gateway", "payment-service")
    assert direct > indirect > 0.0


def test_path_confidence_zero_for_same_or_unreachable():
    graph = fallback_graph()
    assert path_confidence(graph, "payment-service", "payment-service") == 0.0
    assert path_confidence(graph, "payment-service", "user-service") == 0.0
