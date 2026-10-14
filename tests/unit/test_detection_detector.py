"""Unit tests for the anomaly detector (I8)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from common.config import Settings
from detection.detector import AnomalyDetector
from ingestion.schema import NormalizedEvent, Severity, SourceType

BASE = datetime(2026, 10, 11, 10, 0, 0, tzinfo=timezone.utc)


def metric(service: str, name: str, value: float, offset_s: float, idx: int) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=f"m-{service}-{name}-{idx}",
        event_time=BASE + timedelta(seconds=offset_s),
        ingestion_time=BASE + timedelta(seconds=offset_s),
        source_type=SourceType.METRIC,
        event_type="METRIC_SAMPLE",
        service_name=service,
        metric_name=name,
        metric_value=value,
        severity=Severity.INFO,
    )


def error_log(service: str, offset_s: float, idx: int) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=f"l-{service}-{idx}",
        event_time=BASE + timedelta(seconds=offset_s),
        ingestion_time=BASE + timedelta(seconds=offset_s),
        source_type=SourceType.LOG,
        event_type="LOG",
        service_name=service,
        severity=Severity.ERROR,
        message="boom",
    )


def detector() -> AnomalyDetector:
    return AnomalyDetector(Settings(baseline_warmup_points=3, anomaly_z_threshold=4.0))


def test_metric_spike_is_detected():
    events = [
        metric("payment-service", "http_5xx_rate", 0.0, t, i) for i, t in enumerate(range(0, 10))
    ] + [
        metric("payment-service", "http_5xx_rate", 1.0, t, 100 + i)
        for i, t in enumerate(range(10, 20))
    ]

    result = detector().detect(events)

    assert len(result.anomalies) == 1
    anomaly = result.anomalies[0]
    assert anomaly.service == "payment-service"
    assert anomaly.metric == "http_5xx_rate"
    assert anomaly.direction == "up"
    assert anomaly.magnitude > 4.0


def test_flat_metric_is_not_an_anomaly():
    events = [
        metric("user-service", "memory_percent", 35.0, t, i) for i, t in enumerate(range(0, 20))
    ]

    result = detector().detect(events)

    assert result.anomalies == []


def info_log(service: str, offset_s: float, idx: int) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=f"i-{service}-{idx}",
        event_time=BASE + timedelta(seconds=offset_s),
        ingestion_time=BASE + timedelta(seconds=offset_s),
        source_type=SourceType.LOG,
        event_type="LOG",
        service_name=service,
        severity=Severity.INFO,
        message="ok",
    )


def test_derived_error_rate_from_logs_is_detected():
    # A healthy run with only INFO logs, then errors begin - the zero-count
    # leading buckets give the service a baseline to deviate from.
    events = [info_log("order-service", t, i) for i, t in enumerate(range(0, 40, 5))]
    events += [error_log("order-service", t, 200 + i) for i, t in enumerate(range(45, 90, 5))]

    result = detector().detect(events)

    error_anomalies = [a for a in result.anomalies if a.metric == "error_rate"]
    assert error_anomalies
    assert error_anomalies[0].service == "order-service"


def test_downward_spike_is_flagged_as_drop():
    events = [
        metric("payment-service", "throughput", 100.0, t, i) for i, t in enumerate(range(0, 10))
    ] + [
        metric("payment-service", "throughput", 5.0, t, 100 + i) for i, t in enumerate(range(10, 20))
    ]

    result = detector().detect(events)

    assert result.anomalies
    assert result.anomalies[0].direction == "down"


def test_detection_result_groups_and_orders():
    events = [
        metric("a", "x", 0.0, t, i) for i, t in enumerate(range(0, 6))
    ] + [metric("a", "x", 9.0, t, 100 + i) for i, t in enumerate(range(6, 12))]
    events += [metric("b", "y", 0.0, t, i) for i, t in enumerate(range(0, 6))]
    events += [metric("b", "y", 9.0, t, 100 + i) for i, t in enumerate(range(6, 12))]

    result = detector().detect(events)

    assert set(result.by_service()) == {"a", "b"}
    onsets = result.onset_by_service()
    assert set(onsets) == {"a", "b"}
