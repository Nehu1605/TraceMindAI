"""Unit tests for alert grouping (I10, correlation half)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ingestion.schema import NormalizedEvent, Severity, SourceType

from correlation.alerting import group_alerts, grouping_quality
from correlation.constants import NodeType, service_node
from correlation.graph import EventGraph

BASE = datetime(2026, 10, 11, 10, 0, 0, tzinfo=timezone.utc)


def alert(
    event_id: str,
    service: str,
    offset_s: float,
    severity: Severity = Severity.FATAL,
    trace_id: str | None = None,
):
    return NormalizedEvent(
        event_id=event_id,
        event_time=BASE + timedelta(seconds=offset_s),
        ingestion_time=BASE + timedelta(seconds=offset_s + 1),
        source_type=SourceType.ALERT,
        event_type="ALERT",
        service_name=service,
        trace_id=trace_id,
        severity=severity,
        message="alert",
        attributes={"alertname": f"Alert-{event_id}"},
    )


def graph_with_calls(*pairs: tuple[str, str]) -> EventGraph:
    graph = EventGraph()
    for a, b in pairs:
        graph.add_node(service_node(a), NodeType.SERVICE)
        graph.add_node(service_node(b), NodeType.SERVICE)
        graph.increment_call(service_node(a), service_node(b))
    return graph


def test_connected_alerts_in_window_group_into_one_incident():
    graph = graph_with_calls(
        ("api-gateway", "order-service"), ("order-service", "payment-service")
    )
    alerts = [
        alert("a1", "api-gateway", 0),
        alert("a2", "order-service", 1),
        alert("a3", "payment-service", 2),
    ]

    result = group_alerts(alerts, graph, window_seconds=300, max_hops=2)

    assert result.incident_count == 1
    assert result.incidents[0]["services"] == [
        "api-gateway",
        "order-service",
        "payment-service",
    ]
    assert result.reduction_ratio == 3.0
    assert graph.has_node(f"incident:{result.incidents[0]['incident_id']}")


def test_alerts_outside_window_do_not_group():
    graph = graph_with_calls(("order-service", "payment-service"))
    alerts = [
        alert("a1", "payment-service", 0),
        alert("a2", "payment-service", 1000),
    ]

    result = group_alerts(alerts, graph, window_seconds=300, max_hops=2)

    assert result.incident_count == 2


def test_disconnected_service_keeps_its_own_incident():
    graph = graph_with_calls(("api-gateway", "order-service"))
    alerts = [
        alert("a1", "api-gateway", 0),
        alert("a2", "billing-service", 1),
    ]

    result = group_alerts(alerts, graph, window_seconds=300, max_hops=2)

    assert result.incident_count == 2
    assert {tuple(inc["services"]) for inc in result.incidents} == {
        ("api-gateway",),
        ("billing-service",),
    }


def test_max_hops_controls_cross_service_grouping():
    graph = graph_with_calls(
        ("api-gateway", "order-service"), ("order-service", "payment-service")
    )
    alerts = [alert("a1", "api-gateway", 0), alert("a2", "payment-service", 1)]

    near = group_alerts(alerts, graph, window_seconds=300, max_hops=2)
    far = group_alerts(alerts, graph, window_seconds=300, max_hops=1)

    assert near.incident_count == 1
    assert far.incident_count == 2


def test_no_alerts_yields_empty_result():
    result = group_alerts([], EventGraph())
    assert result.incident_count == 0
    assert result.reduction_ratio == 0.0


def test_alerts_sharing_trace_id_group_without_service_link():
    # No CALLS edges at all: only the shared trace id should connect them.
    graph = EventGraph()
    graph.add_node(service_node("api-gateway"), NodeType.SERVICE)
    graph.add_node(service_node("payment-service"), NodeType.SERVICE)
    alerts = [
        alert("a1", "api-gateway", 0, trace_id="trace-1"),
        alert("a2", "payment-service", 1, trace_id="trace-1"),
    ]

    result = group_alerts(alerts, graph, window_seconds=300, max_hops=2)

    assert result.incident_count == 1


def test_grouping_quality_rewards_clean_separation():
    graph = graph_with_calls(("api-gateway", "order-service"))
    alerts = [
        alert("a1", "api-gateway", 0),
        alert("a2", "order-service", 1),
        alert("a3", "billing-service", 2),
    ]
    result = group_alerts(alerts, graph, window_seconds=300, max_hops=2)

    quality = grouping_quality(
        result.incidents,
        {
            "api-gateway": "fault-A",
            "order-service": "fault-A",
            "billing-service": "fault-B",
        },
    )

    assert quality["purity"] == 1.0
    assert quality["impure_incidents"] == 0

    # A merged incident between two faults must be flagged impure.
    merged = [
        {
            "services": ["api-gateway", "billing-service"],
            "service_counts": {"api-gateway": 1, "billing-service": 1},
        }
    ]
    bad = grouping_quality(
        merged,
        {"api-gateway": "fault-A", "billing-service": "fault-B"},
    )
    assert bad["impure_incidents"] == 1
    assert bad["purity"] == 0.5
