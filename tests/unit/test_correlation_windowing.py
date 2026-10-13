"""Unit tests for sliding windows (I7, correlation half)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ingestion.schema import NormalizedEvent, Severity, SourceType

from correlation.windowing import sliding_windows, window_bucket_key

BASE = datetime(2026, 10, 11, 10, 0, 0, tzinfo=timezone.utc)


def event(event_id: str, offset_s: float) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        event_time=BASE + timedelta(seconds=offset_s),
        ingestion_time=BASE + timedelta(seconds=offset_s),
        source_type=SourceType.LOG,
        event_type="LOG",
        service_name="payment-service",
        severity=Severity.INFO,
        message=event_id,
    )


def test_windows_cover_events_and_overlap():
    events = [event(f"e{i}", i * 100) for i in range(6)]  # 0..500s

    windows = list(sliding_windows(events, window_seconds=300, step_seconds=100))

    assert windows
    starts = [start for start, _, _ in windows]
    assert starts == sorted(starts)
    # An event near a window boundary appears in more than one window.
    all_ids = [e.event_id for _, _, bucket in windows for e in bucket]
    assert all_ids.count("e1") >= 2
    # Every event is covered at least once.
    assert {e.event_id for _, _, bucket in windows for e in bucket} == {
        f"e{i}" for i in range(6)
    }


def test_window_content_is_bounded():
    events = [event(f"e{i}", i * 100) for i in range(6)]

    windows = list(sliding_windows(events, window_seconds=300, step_seconds=100))
    start, end, bucket = windows[0]

    assert end - start == timedelta(seconds=300)
    assert all(start <= e.event_time < end for e in bucket)


def test_empty_events_yield_no_windows():
    assert list(sliding_windows([], window_seconds=300, step_seconds=100)) == []


def test_window_bucket_key_is_stable():
    assert window_bucket_key(BASE, 300) == window_bucket_key(
        BASE + timedelta(seconds=100), 300
    )
    assert window_bucket_key(BASE, 300) != window_bucket_key(
        BASE + timedelta(seconds=400), 300
    )
