"""Integration test: detect anomalies on a generated incident dataset (I8)."""

from __future__ import annotations

from detection.detector import AnomalyDetector
from ingestion.pipeline import run_ingestion
from simulator.generate_telemetry import DEGRADE_PRESETS, generate_dataset


def _events(tmp_path, degrade="none", seed=21, requests=40):
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    generate_dataset(raw, seed=seed, requests=requests, degrade=DEGRADE_PRESETS[degrade])
    return run_ingestion(raw, out).events


def test_incident_anomalies_include_the_root_service(tmp_path):
    events = _events(tmp_path)
    result = AnomalyDetector().detect(events)

    services = {a.service for a in result.anomalies}
    # The injected fault is in payment-service; its pool/latency/5xx must fire.
    assert "payment-service" in services
    assert any(
        a.metric == "db_connections_in_use" and a.service == "payment-service"
        for a in result.anomalies
    )
    # Cascade reaches the gateway through derived error signals.
    assert "api-gateway" in services


def test_anomalies_have_evidence_and_onset(tmp_path):
    events = _events(tmp_path)
    result = AnomalyDetector().detect(events)

    assert result.anomalies
    for anomaly in result.anomalies:
        assert anomaly.onset_time is not None
        assert anomaly.magnitude > 0
        assert anomaly.evidence_ids
