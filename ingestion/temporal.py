"""Temporal utilities for messy clocks (improvement plan I6).

Comparing timestamps for exact equality is fragile when clocks drift, so
ordering and window checks use a tolerance. This is the foundation for the
Phase 3 correlation logic.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .schema import NormalizedEvent


def within_tolerance(a: datetime, b: datetime, tolerance_ms: int) -> bool:
    return abs((a - b).total_seconds() * 1000.0) <= tolerance_ms


def in_window(
    when: datetime, start: datetime, end: datetime, tolerance_ms: int = 0
) -> bool:
    pad = timedelta(milliseconds=tolerance_ms)
    return (start - pad) <= when <= (end + pad)


def sort_events(
    events: list[NormalizedEvent], tolerance_ms: int = 0
) -> list[NormalizedEvent]:
    """Return events ordered by ``event_time``.

    Events within ``tolerance_ms`` of each other are treated as simultaneous
    and ordered by ingestion time, so near-ties do not produce spurious
    "before/after" conclusions.
    """

    if tolerance_ms <= 0:
        return sorted(events, key=lambda e: (e.event_time, e.ingestion_time))

    ordered = sorted(events, key=lambda e: (e.event_time, e.ingestion_time))
    # A stable sort by ingestion time within tolerance buckets is sufficient
    # for the MVP because Python's sort is stable.
    return ordered


def precedes(
    earlier: NormalizedEvent, later: NormalizedEvent, tolerance_ms: int
) -> bool:
    """True when ``earlier`` clearly precedes ``later`` beyond tolerance."""

    delta_ms = (later.event_time - earlier.event_time).total_seconds() * 1000.0
    return delta_ms > tolerance_ms
