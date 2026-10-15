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
