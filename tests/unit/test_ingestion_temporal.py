"""Unit tests for clock-tolerant ordering (Phase 2, improvement I6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ingestion.schema import NormalizedEvent, Severity, SourceType
from ingestion.temporal import in_window, precedes, sort_events, time_bucket, within_tolerance

NOW = datetime(2026, 10, 11, 10, 0, 0, tzinfo=timezone.utc)


def _event(name: str, event_offset_ms: float, ingestion_offset_ms: float) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=name,
        event_time=NOW + timedelta(milliseconds=event_offset_ms),
        ingestion_time=NOW + timedelta(milliseconds=ingestion_offset_ms),
        source_type=SourceType.LOG,
        event_type="LOG",
        service_name="payment-service",
        severity=Severity.INFO,
        message=name,
    )


def test_time_bucket_groups_close_events():
    assert time_bucket(NOW + timedelta(milliseconds=100), 1000) == time_bucket(
        NOW + timedelta(milliseconds=300), 1000
    )
    assert time_bucket(NOW + timedelta(milliseconds=100), 1000) != time_bucket(
        NOW + timedelta(milliseconds=2500), 1000
    )


def test_sort_events_without_tolerance_is_strict_event_time_order():
    a = _event("a", 300, 10)
    b = _event("b", 100, 20)

    ordered = sort_events([a, b], tolerance_ms=0)

    assert [e.event_id for e in ordered] == ["b", "a"]


def test_sort_events_orders_within_tolerance_by_ingestion_time():
    # Same 1s bucket: event_time order is a<b, but b arrived first.
    a = _event("a", 100, 5000)
    b = _event("b", 300, 1000)

    ordered = sort_events([a, b], tolerance_ms=1000)

    assert [e.event_id for e in ordered] == ["b", "a"]


def test_sort_events_keeps_distinct_windows_ordered_by_event_time():
    early = _event("early", 100, 9000)
    late = _event("late", 2500, 1)

    ordered = sort_events([late, early], tolerance_ms=1000)

    assert [e.event_id for e in ordered] == ["early", "late"]


def test_tolerance_helpers():
    assert within_tolerance(NOW, NOW + timedelta(milliseconds=100), 200) is True
    assert within_tolerance(NOW, NOW + timedelta(milliseconds=500), 200) is False
    assert in_window(NOW + timedelta(seconds=5), NOW, NOW + timedelta(seconds=10)) is True
    assert in_window(NOW, NOW + timedelta(seconds=1), NOW + timedelta(seconds=10)) is False

    a = _event("a", 0, 0)
    b = _event("b", 300, 0)
    assert precedes(a, b, tolerance_ms=200) is True
    assert precedes(b, a, tolerance_ms=200) is False
