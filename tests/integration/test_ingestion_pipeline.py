"""Integration test: generate raw telemetry, run the ingestion pipeline."""

from __future__ import annotations

import json

from ingestion.pipeline import run_ingestion
from ingestion.schema import NormalizedEvent, SourceType
from simulator.generate_telemetry import DEGRADE_PRESETS, generate_dataset


def test_clean_dataset_ingests_without_quarantine(tmp_path):
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    generate_dataset(raw, seed=1, requests=20, degrade=DEGRADE_PRESETS["none"])

    result = run_ingestion(raw, out)

    assert result.quarantined == []
    assert result.quality_report.valid_events == len(result.events)
    assert result.quality_report.missing_trace_id == 0
    assert result.quality_report.broken_trace_links == 0
    assert result.quality_report.late_events == 0
    assert result.quality_report.clock_skew_suspected == 0


def test_pipeline_writes_all_outputs(tmp_path):
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    generate_dataset(raw, seed=2, requests=20, degrade=DEGRADE_PRESETS["none"])

    run_ingestion(raw, out)

    assert (out / "normalized_events.jsonl").exists()
    assert (out / "quarantined.jsonl").exists()
    assert (out / "quality_report.json").exists()
    assert (out / "summary.json").exists()


def test_normalized_events_round_trip_through_jsonl(tmp_path):
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    generate_dataset(raw, seed=3, requests=20, degrade=DEGRADE_PRESETS["none"])
    run_ingestion(raw, out)

    lines = (out / "normalized_events.jsonl").read_text(encoding="utf-8").splitlines()
    events = [NormalizedEvent.from_json(line) for line in lines if line.strip()]

    assert events
    assert all(isinstance(event.event_time, type(events[0].event_time)) for event in events)
    assert {event.source_type for event in events} >= {
        SourceType.TRACE,
        SourceType.LOG,
        SourceType.METRIC,
        SourceType.DEPLOYMENT,
        SourceType.ALERT,
    }


def test_events_are_ordered_by_event_time(tmp_path):
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    generate_dataset(raw, seed=4, requests=20, degrade=DEGRADE_PRESETS["none"])

    result = run_ingestion(raw, out)

    times = [event.event_time for event in result.events]
    assert times == sorted(times)


def test_incident_window_contains_error_events(tmp_path):
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    generate_dataset(raw, seed=5, requests=40, degrade=DEGRADE_PRESETS["none"])

    result = run_ingestion(raw, out)

    error_logs = [
        event
        for event in result.events
        if event.source_type == SourceType.LOG and event.severity.value == "ERROR"
    ]
    assert error_logs
    assert all(event.event_type == "DB_CONNECTION_TIMEOUT" or event.event_type == "HTTP_5XX" for event in error_logs)

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["error_events"] >= 1
    assert summary["alert_events"] >= 1
    assert summary["deployment_events"] >= 1
