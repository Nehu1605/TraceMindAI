"""Degradation test: the pipeline must tolerate messy telemetry (I6).

Generates the same incident twice - once clean, once with planted
data-quality defects - and asserts that:

* the clean run produces a clean quality report;
* the messy run detects and reports each planted defect;
* the messy run still yields usable events (it degrades gracefully rather
  than discarding the batch).
"""

from __future__ import annotations

from ingestion.pipeline import run_ingestion
from ingestion.schema import SourceType
from simulator.generate_telemetry import DEGRADE_PRESETS, generate_dataset


def _ingest(tmp_path, degrade, seed):
    raw = tmp_path / f"raw-{degrade}"
    out = tmp_path / f"out-{degrade}"
    generate_dataset(raw, seed=seed, requests=40, degrade=DEGRADE_PRESETS[degrade])
    return run_ingestion(raw, out)


def test_clean_dataset_is_clean(tmp_path):
    result = _ingest(tmp_path, "none", seed=10)
    report = result.quality_report

    assert result.quarantined == []
    assert report.missing_trace_id == 0
    assert report.clock_skew_suspected == 0
    assert report.late_events == 0
    assert report.broken_trace_links == 0
    assert report.unknown_service == 0


def test_messy_dataset_defects_are_reported(tmp_path):
    result = _ingest(tmp_path, "heavy", seed=11)
    report = result.quality_report

    assert report.valid_events > 0
    assert report.missing_trace_id_rate > 0.0
    assert report.clock_skew_suspected > 0
    assert report.late_events > 0
    assert report.broken_trace_links >= 1
    assert report.unknown_service >= 1
    assert report.quarantine_reasons.get("invalid_timestamp", 0) >= 1
    assert report.quarantine_reasons.get("out_of_range_value", 0) >= 1
    assert report.quarantine_reasons.get("unknown_service", 0) >= 1
    assert report.quarantine_reasons.get("duplicate_event", 0) >= 1


def test_messy_dataset_still_produces_all_evidence_types(tmp_path):
    result = _ingest(tmp_path, "heavy", seed=12)

    present = {event.source_type for event in result.events}

    assert present >= {
        SourceType.TRACE,
        SourceType.LOG,
        SourceType.METRIC,
        SourceType.DEPLOYMENT,
        SourceType.ALERT,
    }


def test_generation_is_deterministic(tmp_path):
    manifest_a = generate_dataset(
        tmp_path / "a", seed=99, requests=30, degrade=DEGRADE_PRESETS["light"]
    )
    manifest_b = generate_dataset(
        tmp_path / "b", seed=99, requests=30, degrade=DEGRADE_PRESETS["light"]
    )

    assert manifest_a["counts"] == manifest_b["counts"]
