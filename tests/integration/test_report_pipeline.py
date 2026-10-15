"""Integration test: end-to-end report generation (I4/I11/I13)."""

from __future__ import annotations

from report.pipeline import build_report
from rca.engine import RCAEngine
from ingestion.pipeline import run_ingestion
from simulator.generate_telemetry import DEGRADE_PRESETS, generate_dataset


def _events(tmp_path, degrade="none", seed=21, requests=40):
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    generate_dataset(raw, seed=seed, requests=requests, degrade=DEGRADE_PRESETS[degrade])
    return run_ingestion(raw, out).events


def test_report_generates_all_sections(tmp_path):
    events = _events(tmp_path)
    rca = RCAEngine().analyze(events)
    report = build_report("incident-001", rca)

    assert report.incident_id == "incident-001"
    assert report.narrative
    assert "offline" in report.generators
    assert "llm" in report.generators
    assert report.critic
    assert report.playbook is not None
    assert report.playbook.dry_run is True


def test_report_playbook_matches_incident_type(tmp_path):
    events = _events(tmp_path)
    rca = RCAEngine().analyze(events)
    report = build_report("incident-001", rca)

    # Payment DB pool exhaustion should select the db playbook
    assert report.playbook.playbook == "db_pool_exhaustion"
    assert len(report.playbook.steps) == 2


def test_report_evidence_map_links_to_rca(tmp_path):
    events = _events(tmp_path)
    rca = RCAEngine().analyze(events)
    report = build_report("incident-001", rca)

    assert "payment-service" in report.evidence_map
    assert len(report.evidence_map["payment-service"]) > 0


def test_report_can_be_serialized(tmp_path):
    events = _events(tmp_path)
    rca = RCAEngine().analyze(events)
    report = build_report("incident-001", rca)

    # Round-trip through JSON
    import json

    json.dumps(report.to_dict())