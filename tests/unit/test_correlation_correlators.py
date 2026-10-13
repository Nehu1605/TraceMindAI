"""Unit tests for the correlators (Phase 3, I6 fallback links)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ingestion.schema import NormalizedEvent, Severity, SourceType

from correlation.constants import EdgeType, commit_node, service_node, span_node
from correlation.correlators import Correlators
from correlation.graph import EventGraph

BASE = datetime(2026, 10, 11, 10, 0, 0, tzinfo=timezone.utc)


def span(
    span_id: str,
    service: str,
    offset_ms: float,
    trace_id: str | None = "t1",
    parent: str | None = None,
    status: int = 200,
) -> NormalizedEvent:
    severity = Severity.ERROR if status >= 500 else Severity.INFO
    return NormalizedEvent(
        event_id=f"evt-{span_id}",
        event_time=BASE + timedelta(milliseconds=offset_ms),
        ingestion_time=BASE + timedelta(milliseconds=offset_ms + 5),
        source_type=SourceType.TRACE,
        event_type="SPAN",
        service_name=service,
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent,
        severity=severity,
        message=f"op-{span_id}",
        status_code=status,
        duration_ms=10.0,
        source_reference=f"traces.jsonl:{span_id}",
    )


def log(
    event_id: str,
    service: str,
    offset_ms: float,
    trace_id: str | None = None,
    span_id: str | None = None,
    severity: Severity = Severity.ERROR,
    event_type: str = "DB_CONNECTION_TIMEOUT",
) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        event_time=BASE + timedelta(milliseconds=offset_ms),
        ingestion_time=BASE + timedelta(milliseconds=offset_ms + 5),
        source_type=SourceType.LOG,
        event_type=event_type,
        service_name=service,
        trace_id=trace_id,
        span_id=span_id,
        severity=severity,
        message="log line",
        source_reference=f"logs.jsonl:{event_id}",
    )


def _correlate(events):
    graph = EventGraph()
    c = Correlators(graph, window_seconds=30.0)
    c.correlate_spans(events)
    c.correlate_logs(events)
    c.correlate_metrics(events)
    c.correlate_deployments(events)
    c.correlate_alerts(events)
    return graph, c


def test_span_parent_child_and_service_calls():
    events = [
        span("g", "api-gateway", 0, parent=None),
        span("o", "order-service", 3, parent="g"),
    ]

    graph, _ = _correlate(events)

    assert graph.has_node(span_node("g"))
    assert (span_node("g"), span_node("o")) in graph.edges_of_type(EdgeType.PARENT_OF)
    calls = graph.service_dependencies()
    assert ("service:api-gateway", "service:order-service", 1) in calls


def test_log_direct_link_when_trace_present():
    events = [span("p", "payment-service", 0, status=503)]
    events.append(log("l1", "payment-service", 5, trace_id="t1", span_id="p"))

    graph, counts = _correlate(events)

    assert (span_node("p"), "log:l1") in graph.edges_of_type(EdgeType.GENERATED)
    assert counts.counts["direct"] >= 1


def test_log_inferred_link_without_trace_id():
    events = [span("p", "payment-service", 0, status=503)]
    events.append(log("l2", "payment-service", 100, trace_id=None))

    graph, counts = _correlate(events)

    edge = graph.graph[span_node("p")]["log:l2"][EdgeType.GENERATED.value]
    assert edge["evidence_quality"] == "inferred"
    assert counts.counts["inferred"] == 1


def test_log_time_only_link_when_not_an_error():
    events = [span("p", "payment-service", 0, status=200)]
    events.append(log("l3", "payment-service", 100, severity=Severity.INFO, event_type="LOG"))

    graph, counts = _correlate(events)

    edge = graph.graph[span_node("p")]["log:l3"][EdgeType.GENERATED.value]
    assert edge["evidence_quality"] == "time_only"
    assert counts.counts["time_only"] >= 1


def test_log_without_any_span_attaches_to_service():
    graph, counts = _correlate([log("l4", "user-service", 0, trace_id=None)])

    assert (service_node("user-service"), "log:l4") in graph.edges_of_type(EdgeType.GENERATED)


def test_deployment_links_commit_and_service():
    deployment = NormalizedEvent(
        event_id="evt-dep",
        event_time=BASE,
        ingestion_time=BASE + timedelta(seconds=1),
        source_type=SourceType.DEPLOYMENT,
        event_type="DEPLOYMENT",
        service_name="payment-service",
        deployment_id="dep-1",
        severity=Severity.INFO,
        attributes={"commit_sha": "c0ffee1d00m3"},
    )

    graph, _ = _correlate([deployment])

    assert ("deployment:dep-1", service_node("payment-service")) in graph.edges_of_type(
        EdgeType.DEPLOYED_TO
    )
    assert ("deployment:dep-1", commit_node("c0ffee1d00m3")) in graph.edges_of_type(
        EdgeType.MODIFIED
    )


def test_metric_and_alert_links():
    metric = NormalizedEvent(
        event_id="evt-m",
        event_time=BASE,
        ingestion_time=BASE,
        source_type=SourceType.METRIC,
        event_type="METRIC_SAMPLE",
        service_name="payment-service",
        metric_name="http_5xx_rate",
        metric_value=1.0,
        severity=Severity.INFO,
    )
    alert = NormalizedEvent(
        event_id="evt-a",
        event_time=BASE,
        ingestion_time=BASE,
        source_type=SourceType.ALERT,
        event_type="ALERT",
        service_name="payment-service",
        severity=Severity.FATAL,
        message="5xx",
        attributes={"alertname": "Payment5xxRate"},
    )

    graph, _ = _correlate([metric, alert])

    assert (service_node("payment-service"), "metric:evt-m") in graph.edges_of_type(
        EdgeType.GENERATED
    )
    assert ("alert:evt-a", service_node("payment-service")) in graph.edges_of_type(
        EdgeType.OBSERVED_DURING
    )
