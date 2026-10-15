"""Temporal utilities for messy clocks (improvement plan I6).

Comparing timestamps for exact equality is fragile when clocks drift, so
ordering and window checks use a tolerance. This is the foundation for the
Phase 3 correlation logic.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from .schema import NormalizedEvent


def within_tolerance(a: datetime, b: datetime, tolerance_ms: int) -> bool:
    return abs((a - b).total_seconds() * 1000.0) <= tolerance_ms


def in_window(
    when: datetime, start: datetime, end: datetime, tolerance_ms: int = 0
) -> bool:
    pad = timedelta(milliseconds=tolerance_ms)
    return (start - pad) <= when <= (end + pad)


def time_bucket(event_time: datetime, tolerance_ms: int) -> int:
    """Floor ``event_time`` into a fixed-width tolerance window."""

    if tolerance_ms <= 0:
        return 0
    return math.floor(event_time.timestamp() * 1000.0 / tolerance_ms)


def sort_events(
    events: list[NormalizedEvent], tolerance_ms: int = 0
) -> list[NormalizedEvent]:
    """Return events in a clock-tolerant order.

    ``event_time`` is bucketed into fixed ``tolerance_ms`` windows. Events in
    the same window are treated as simultaneous and ordered by *ingestion*
    time, because sub-tolerance differences between two clocks are not
    trustworthy. Events in different windows are ordered by ``event_time``.
    This is what keeps near-ties from producing spurious "before/after"
    conclusions when clocks drift.
    """

    if tolerance_ms <= 0:
        return sorted(events, key=lambda e: (e.event_time, e.ingestion_time))

    return sorted(
        events,
        key=lambda e: (
            time_bucket(e.event_time, tolerance_ms),
            e.ingestion_time,
            e.event_time,
        ),
    )


def precedes(
    earlier: NormalizedEvent, later: NormalizedEvent, tolerance_ms: int
) -> bool:
    """True when ``earlier`` clearly precedes ``later`` beyond tolerance."""

    delta_ms = (later.event_time - earlier.event_time).total_seconds() * 1000.0
    return delta_ms > tolerance_ms
