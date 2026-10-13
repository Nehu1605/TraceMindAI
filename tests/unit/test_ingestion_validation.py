"""Unit tests for the event validator and quarantine (Phase 2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ingestion.schema import NormalizedEvent, Severity, SourceType
from ingestion.validation import (
    REASON_DUPLICATE,
    REASON_MISSING_REQUIRED_FIELD,
    REASON_OUT_OF_RANGE,
    REASON_UNKNOWN_SERVICE,
    MAX_DURATION_MS,
    EventValidator,
    detect_broken_trace_links,
)

NOW = datetime(2026, 10, 11, 10, 0, 0, tzinfo=timezone.utc)


def make_event(**overrides) -> NormalizedEvent:
    base = dict(
        event_id="evt-1",
        event_time=NOW,
        ingestion_time=NOW + timedelta(milliseconds=10),
        source_type=SourceType.TRACE,
        event_type="SPAN",
        service_name="payment-service",
        trace_id="t1",
        span_id="s1",
        severity=Severity.INFO,
    )
    base.update(overrides)
    return NormalizedEvent(**base)


def validator() -> EventValidator:
    return EventValidator(
        known_services={"payment-service", "api-gateway"},
        late_threshold_seconds=60.0,
        clock_skew_threshold_ms=500,
        dedup_window_seconds=300.0,
    )


def test_valid_event_has_no_reasons():
    assert validator().check(make_event()) == []


def test_missing_required_field_is_flagged():
    reasons = validator().check(make_event(trace_id=None))
    assert REASON_MISSING_REQUIRED_FIELD in reasons


def test_unknown_service_is_flagged():
    reasons = validator().check(make_event(service_name="payment_svc_v2"))
    assert REASON_UNKNOWN_SERVICE in reasons


def test_out_of_range_duration_and_status():
    reasons = validator().check(
        make_event(duration_ms=MAX_DURATION_MS + 1, status_code=999)
    )
    assert reasons.count(REASON_OUT_OF_RANGE) == 2


def test_duplicate_event_is_only_flagged_once():
    v = validator()
    assert v.check(make_event()) == []
    assert REASON_DUPLICATE in v.check(make_event())


def test_repeat_outside_dedup_window_is_not_a_duplicate():
    v = EventValidator(known_services={"payment-service"}, dedup_window_seconds=10.0)
    first = make_event(event_time=NOW)
    later = make_event(event_time=NOW + timedelta(seconds=30))

    assert v.check(first) == []
    assert v.check(later) == []


def test_repeat_inside_dedup_window_is_a_duplicate():
    v = EventValidator(known_services={"payment-service"}, dedup_window_seconds=300.0)
    first = make_event(event_time=NOW)
    near = make_event(event_time=NOW + timedelta(seconds=5))

    assert v.check(first) == []
    assert REASON_DUPLICATE in v.check(near)


def test_late_event_is_annotated_not_quarantined():
    event = make_event(ingestion_time=NOW + timedelta(seconds=120))
    assert validator().check(event) == []
    assert event.is_late is True


def test_clock_skew_is_annotated_not_quarantined():
    event = make_event(ingestion_time=NOW - timedelta(milliseconds=700))
    assert validator().check(event) == []
    assert event.clock_skew_suspected is True


def test_detect_broken_trace_links():
    parent = make_event(event_id="evt-parent", trace_id="t1", span_id="root", parent_span_id=None)
    child = make_event(event_id="evt-child", trace_id="t1", span_id="c1", parent_span_id="root")
    orphan = make_event(event_id="evt-orphan", trace_id="t2", span_id="o1", parent_span_id="missing")

    broken = detect_broken_trace_links([parent, child, orphan])

    assert broken == 1
    assert orphan.attributes.get("broken_trace_link") is True
    assert child.attributes.get("broken_trace_link") is None
