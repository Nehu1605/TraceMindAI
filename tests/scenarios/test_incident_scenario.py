"""Scenario test: the ground-truth model matches the injected fault behavior.

This validates the data contract used by later phases without requiring a
live stack: given the scenario definition, the expected root cause and
affected services are recorded consistently.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"


def test_incident_scenarios_are_well_formed():
    scenarios = json.loads((DATA_DIR / "incident_scenarios.json").read_text())["scenarios"]
    ids = {scenario["id"] for scenario in scenarios}
    assert "payment-db-conn-exhaustion-001" in ids

    primary = next(s for s in scenarios if s["id"] == "payment-db-conn-exhaustion-001")
    assert primary["fault_mode"] == "db_conn_leak"
    assert primary["root_cause_service"] == "payment-service"
    assert set(primary["affected_services"]) == {
        "payment-service",
        "order-service",
        "api-gateway",
    }


def test_ground_truth_template_has_required_fields():
    truth = json.loads((DATA_DIR / "scenario_ground_truth.json").read_text())
    for field in (
        "scenario_id",
        "injected_cause",
        "root_cause_service",
        "incident_start_time",
        "affected_services",
    ):
        assert field in truth


def test_deployments_csv_has_header():
    content = (DATA_DIR / "deployments.csv").read_text().strip().splitlines()
    assert content[0].startswith("deployment_id,service_name,timestamp")
    assert len(content) > 1


def test_deployments_csv_includes_a_decoy_deployment():
    rows = (DATA_DIR / "deployments.csv").read_text().strip().splitlines()[1:]
    services = [row.split(",")[1] for row in rows]

    # I1: the environment must contain a decoy deploy on a service that is not
    # the root cause, so commit attribution cannot just blame the latest deploy.
    assert "user-service" in services
    assert "payment-service" in services


def test_ground_truth_records_decoy_deployments():
    truth = json.loads((DATA_DIR / "scenario_ground_truth.json").read_text())
    assert truth["decoy_deployments"]
    assert truth["decoy_deployments"][0]["service_name"] != truth["root_cause_service"]


def test_generated_alerts_cover_rate_latency_cpu_and_pool(tmp_path):
    import json

    from simulator.generate_telemetry import DEGRADE_PRESETS, generate_dataset

    generate_dataset(tmp_path / "raw", seed=5, requests=20, degrade=DEGRADE_PRESETS["none"])
    alerts = json.loads((tmp_path / "raw" / "alerts.json").read_text())["alerts"]
    names = " ".join(str(a["alertname"]) for a in alerts).lower()
    # I10 lists error rate, latency, CPU and pool usage among the alert sources.
    for token in ("cpu", "latency", "pool", "5xx"):
        assert token in names, token


def test_generated_dataset_has_a_later_decoy_deployment(tmp_path):
    import csv

    from simulator.generate_telemetry import DEGRADE_PRESETS, generate_dataset

    generate_dataset(tmp_path / "raw", seed=5, requests=20, degrade=DEGRADE_PRESETS["none"])
    with (tmp_path / "raw" / "deployments.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    decoy = next(row for row in rows if row["service_name"] == "user-service")
    incident = next(row for row in rows if row["service_name"] == "payment-service")
    # The decoy lands later than the real fault deploy (B4 trap).
    assert decoy["timestamp"] > incident["timestamp"]
