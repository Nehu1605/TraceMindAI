"""Validation and quarantine.

Invalid records are never silently dropped: they are quarantined with an
explicit reason so the data-quality report can explain what was wrong. That
is a stated requirement of the methodology ("preserve invalid records or
quarantine them with a clear reason").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .schema import NormalizedEvent, SourceType

REASON_MISSING_REQUIRED_FIELD = "missing_required_field"
REASON_INVALID_TIMESTAMP = "invalid_timestamp"
REASON_UNKNOWN_SERVICE = "unknown_service"
REASON_OUT_OF_RANGE = "out_of_range_value"
REASON_DUPLICATE = "duplicate_event"
REASON_MALFORMED_JSON = "malformed_json"

# Maximum plausible span/request duration (1 hour) before we distrust it.
MAX_DURATION_MS = 3_600_000.0

_REQUIRED_FIELDS: dict[SourceType, tuple[str, ...]] = {
    SourceType.TRACE: ("trace_id", "span_id", "service_name"),
    SourceType.LOG: ("message",),
    SourceType.METRIC: ("metric_name", "metric_value"),
    SourceType.DEPLOYMENT: ("deployment_id", "service_name"),
    SourceType.ALERT: ("event_type",),
}


@dataclass
class QuarantineRecord:
    source_reference: str
    reasons: list[str]
    raw: dict[str, Any]


@dataclass
class ValidationOutcome:
    valid: list[NormalizedEvent] = field(default_factory=list)
    quarantined: list[QuarantineRecord] = field(default_factory=list)


class EventValidator:
    def __init__(
        self,
        known_services: set[str] | None = None,
        late_threshold_seconds: float = 60.0,
        clock_skew_threshold_ms: int = 500,
    ) -> None:
        self.known_services = known_services or set()
        self.late_threshold_seconds = late_threshold_seconds
        self.clock_skew_threshold_ms = clock_skew_threshold_ms
        self._seen_ids: set[str] = set()

    def annotate(self, event: NormalizedEvent) -> None:
        """Set timing-quality flags (late arrival, suspected clock skew)."""

        lag_seconds = (event.ingestion_time - event.event_time).total_seconds()
        event.is_late = lag_seconds > self.late_threshold_seconds

        skew_ms = (event.event_time - event.ingestion_time).total_seconds() * 1000.0
        event.clock_skew_suspected = skew_ms > self.clock_skew_threshold_ms

    def field_reasons(self, event: NormalizedEvent) -> list[str]:
        reasons: list[str] = []
        required = _REQUIRED_FIELDS.get(event.source_type, ())
        for field_name in required:
            if getattr(event, field_name) in (None, ""):
                reasons.append(REASON_MISSING_REQUIRED_FIELD)
                break

        if event.service_name and event.service_name not in self.known_services:
            reasons.append(REASON_UNKNOWN_SERVICE)

        if event.duration_ms is not None and not (0.0 <= event.duration_ms <= MAX_DURATION_MS):
            reasons.append(REASON_OUT_OF_RANGE)
        if event.status_code is not None and not (100 <= event.status_code <= 599):
            reasons.append(REASON_OUT_OF_RANGE)
        if event.metric_value is not None and event.metric_value < 0 and event.source_type == SourceType.METRIC:
            # Negative rates/durations are not physically meaningful.
            if event.attributes.get("allow_negative") is not True:
                reasons.append(REASON_OUT_OF_RANGE)

        return reasons

    def is_duplicate(self, event: NormalizedEvent) -> bool:
        if event.event_id in self._seen_ids:
            return True
        self._seen_ids.add(event.event_id)
        return False

    def check(self, event: NormalizedEvent) -> list[str]:
        """Annotate the event and return the reasons it should be quarantined.

        Returns an empty list when the event is valid.
        """

        self.annotate(event)
        reasons = self.field_reasons(event)
        if not reasons and self.is_duplicate(event):
            reasons = [REASON_DUPLICATE]
        return reasons


def detect_broken_trace_links(events: list[NormalizedEvent]) -> int:
    """Flag spans whose parent span is missing from the batch.

    Dropped spans are expected under sampling, so a broken link is recorded
    as a quality signal on the event rather than treated as invalid.
    """

    span_ids = {e.span_id for e in events if e.source_type == SourceType.TRACE and e.span_id}
    broken = 0
    for event in events:
        if (
            event.source_type == SourceType.TRACE
            and event.parent_span_id
            and event.parent_span_id not in span_ids
        ):
            event.attributes["broken_trace_link"] = True
            broken += 1
    return broken
