"""Unit tests for log-template mining and log-volume reduction (I10)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ingestion.schema import NormalizedEvent, Severity, SourceType

from correlation.log_reduction import (
    LogReductionResult,
    mine_templates,
    reduce_logs,
    template_of,
    windows_from_incidents,
)

BASE = datetime(2026, 10, 11, 10, 0, 0, tzinfo=timezone.utc)


def log(
    event_id: str,
    message: str,
    offset_s: float = 0,
    severity: Severity = Severity.INFO,
    service: str = "payment-service",
) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        event_time=BASE + timedelta(seconds=offset_s),
        ingestion_time=BASE + timedelta(seconds=offset_s + 1),
        source_type=SourceType.LOG,
        event_type="LOG",
        service_name=service,
        severity=severity,
        message=message,
    )


def span(event_id: str) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        event_time=BASE,
        ingestion_time=BASE,
        source_type=SourceType.TRACE,
        event_type="SPAN",
        service_name="payment-service",
    )


def test_template_collapses_numbers_and_ids():
    a = template_of("connection pool exhausted (active=9) attempt 3")
    b = template_of("connection pool exhausted (active=10) attempt 7")
    assert a == b
    assert template_of("trace 3f2a9b1c8d failed") == template_of("trace 9a8b7c6d5e failed")
    assert template_of(None) == ""


def test_mine_templates_counts_repeats():
    events = [
        log("l1", "pool exhausted active=9"),
        log("l2", "pool exhausted active=10"),
        log("l3", "started up"),
    ]

    templates = mine_templates(events)

    top = templates[0]
    assert top["count"] == 2
    assert top["service"] == "payment-service"
    assert top["bytes"] > 0
    assert len(templates) == 2


def test_reduce_logs_keeps_incident_window_and_errors_drops_rest():
    events = [
        log("l1", "noise", offset_s=0),
        log("l2", "noise", offset_s=5),
        log("l3", "inside incident", offset_s=100),
        log("l4", "boom failed", offset_s=5, severity=Severity.ERROR),
        span("s1"),
    ]
    windows = windows_from_incidents(
        [{"start_time": (BASE + timedelta(seconds=99)).isoformat(),
          "end_time": (BASE + timedelta(seconds=101)).isoformat()}],
        pad_seconds=0.0,
    )

    result = reduce_logs(events, keep_windows=windows, sample_rate=0.0)

    kept_ids = {e.event_id for e in result.kept_events}
    assert kept_ids == {"l3", "l4", "s1"}
    assert result.log_count_total == 4
    assert result.log_count_retained == 2
    assert result.log_reduction_pct == 50.0
    assert result.bytes_ingested > result.bytes_retained
    assert result.bytes_reduction_pct > 0.0
    # "noise" (x2) collapses to one template, plus the incident and error lines.
    assert result.template_count == 3


def test_reduce_logs_sampling_is_deterministic_and_increases_retention():
    events = [log(f"l{i}", f"line {i}", offset_s=i) for i in range(50)]

    dropped = reduce_logs(events, keep_windows=[], sample_rate=0.0)
    sampled = reduce_logs(events, keep_windows=[], sample_rate=0.5)
    sampled_again = reduce_logs(events, keep_windows=[], sample_rate=0.5)

    assert dropped.log_count_retained == 0
    assert 0 < sampled.log_count_retained < 50
    assert [e.event_id for e in sampled.kept_events] == [
        e.event_id for e in sampled_again.kept_events
    ]
    assert 0 < sampled.bytes_reduction_pct < 100


def test_template_reduction_collapses_distinct_lines():
    events = [log(f"l{i}", f"processed order {i} in {i * 3} ms") for i in range(20)]

    result = reduce_logs(events, keep_windows=[])

    assert result.unique_lines == 20
    assert result.template_count == 1
    assert result.template_reduction_pct == 95.0


def test_log_reduction_result_handles_empty_input():
    result = reduce_logs([])
    assert isinstance(result, LogReductionResult)
    assert result.bytes_reduction_pct == 0.0
    assert result.log_reduction_pct == 0.0
