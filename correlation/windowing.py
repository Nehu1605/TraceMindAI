"""Sliding time windows (improvement I7, correlation half).

Correlation should not wait for a fixed batch to close: it runs over the last
N seconds of events as a sliding window, so a growing incident is correlated
as soon as it is observable. This module provides the window iterator the
pipeline (and later the detector) consumes.
"""

from __future__ import annotations

from bisect import bisect_left
from datetime import datetime, timedelta
from typing import Iterator

from ingestion.schema import NormalizedEvent


def sliding_windows(
    events: list[NormalizedEvent],
    window_seconds: float = 300.0,
    step_seconds: float = 60.0,
) -> Iterator[tuple[datetime, datetime, list[NormalizedEvent]]]:
    """Yield ``(window_start, window_end, events_in_window)`` tuples.

    Windows advance by ``step_seconds`` and cover ``window_seconds`` each, so
    consecutive windows overlap. Only windows that contain at least one event
    are yielded.
    """

    if not events:
        return
    ordered = sorted(events, key=lambda e: e.event_time)
    times = [e.event_time for e in ordered]
    window = timedelta(seconds=window_seconds)
    step = timedelta(seconds=step_seconds)

    start = ordered[0].event_time
    last = ordered[-1].event_time
    while start <= last:
        end = start + window
        lo = bisect_left(times, start)
        hi = bisect_left(times, end)
        in_window = ordered[lo:hi]
        if in_window:
            yield start, end, in_window
        start += step


def window_bucket_key(when: datetime, window_seconds: float) -> int:
    """Stable integer key for the window a timestamp falls into."""

    return int(when.timestamp() // window_seconds)
