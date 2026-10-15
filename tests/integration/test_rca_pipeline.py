"""Integration test: end-to-end RCA on a generated incident dataset (I2/I8/I9/I12)."""

from __future__ import annotations

from rca.engine import RCAEngine
from ingestion.pipeline import run_ingestion
from simulator.generate_telemetry import DEGRADE_PRESETS, generate_dataset


def _events(tmp_path, degrade="none", seed=21, requests=40):
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    generate_dataset(raw, seed=seed, requests=requests, degrade=DEGRADE_PRESETS[degrade])
    return run_ingestion(raw, out).events


def test_rca_finds_payment_service_as_root(tmp_path):
    events = _events(tmp_path)
    report = RCAEngine().analyze(events)

    assert report.top_cause is not None
    assert report.top_cause.service == "payment-service"
    assert report.top_cause.confidence == "high"
    assert report.top_cause.deployment is not None
    assert report.top_cause.deployment.commit_sha == "c0ffee1d00m3"


def test_baselines_are_computed_and_b4_falls_for_decoy(tmp_path):
    events = _events(tmp_path)
    report = RCAEngine().analyze(events)

    b4 = report.baselines["B4_latest_deploy"]
    assert b4 and b4[0] == "user-service"


def test_rca_report_has_explainable_top_k(tmp_path):
    events = _events(tmp_path)
    report = RCAEngine().analyze(events)

    assert len(report.candidates) >= 3
    for candidate in report.candidates[:3]:
        assert candidate.evidence_ids
        assert candidate.rationale
        assert candidate.components


def test_top_k_explainability(tmp_path):
    events = _events(tmp_path)
    report = RCAEngine().analyze(events)

    assert len(report.candidates) >= 3
    for candidate in report.candidates[:3]:
        assert candidate.evidence_ids
        assert candidate.rationale
        assert candidate.components