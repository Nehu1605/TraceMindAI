"""Unit tests for the data-quality report (Phase 2, improvement I6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ingestion.quality import build_quality_report
from ingestion.schema import (
    EvidenceQuality,
    NormalizedEvent,
    Severity,
    SourceType,
)
from ingestion.validation import QuarantineRecord

NOW = datetime(2026, 10, 11, 10, 0, 0, tzinfo=timezone.utc)


def _event(**overrides) -> NormalizedEvent:
    base = dict(
        event_id="evt",
        event_time=NOW,
        ingestion_time=NOW,
        source_type=SourceType.LOG,
        event_type="LOG",
        service_name="payment-service",
        severity=Severity.INFO,
        evidence_quality=EvidenceQuality.DIRECT,
    )
    base.update(overrides)
    return NormalizedEvent(**base)


def test_quality_report_counts_and_rates():
    events = [
        _event(event_id="a", trace_id="t1", span_id="s1"),
        _event(event_id="b", is_late=True),
        _event(
            event_id="c",
            evidence_quality=EvidenceQuality.TIME_ONLY,
            attributes={"broken_trace_link": True},
        ),
    ]
    quarantined = [
        QuarantineRecord("logs.jsonl:2", ["unknown_service"], {}),
        QuarantineRecord("logs.jsonl:3", ["duplicate_event", "unknown_service"], {}),
    ]

    report = build_quality_report(events, quarantined, total_raw=5)

    assert report.valid_events == 3
    assert report.quarantined == 2
    assert report.quarantine_reasons == {"unknown_service": 2, "duplicate_event": 1}
    assert report.late_events == 1
    assert report.broken_trace_links == 1
    assert report.missing_trace_id == 2
    assert report.to_dict()["missing_trace_id_rate"] == round(2 / 3, 4)
    assert report.evidence_quality["time_only"] == 1


def test_quality_report_handles_empty_input():
    report = build_quality_report([], [], total_raw=0)

    assert report.valid_events == 0
    assert report.missing_trace_id_rate == 0.0
    assert report.to_dict()["quarantine_rate"] == 0.0


def test_quality_report_ingestion_lag_percentiles():
    events = [
        _event(event_id="a", ingestion_time=NOW + timedelta(milliseconds=10)),
        _event(event_id="b", ingestion_time=NOW + timedelta(milliseconds=20)),
        _event(event_id="c", ingestion_time=NOW + timedelta(milliseconds=30)),
    ]

    report = build_quality_report(events, [], total_raw=3)

    assert report.ingestion_lag_ms_p50 == 20.0
    assert report.ingestion_lag_ms_p95 == 30.0
