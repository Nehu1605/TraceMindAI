"""Scenario test: alert grouping quality on the injected incident (I10)."""

from __future__ import annotations

from datetime import timedelta

from ingestion.pipeline import run_ingestion
from ingestion.schema import NormalizedEvent, Severity, SourceType
from simulator.generate_telemetry import DEGRADE_PRESETS, generate_dataset

from correlation.builder import correlate_events


def _incident_events(tmp_path):
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    generate_dataset(raw, seed=31, requests=40, degrade=DEGRADE_PRESETS["none"])
    return run_ingestion(raw, out).events


def test_incident_alerts_collapse_and_a_decoy_stays_separate(tmp_path):
    events = _incident_events(tmp_path)
    alerts = [e for e in events if e.source_type == SourceType.ALERT]
    assert alerts

    # A decoy alert on a service that is not in the call graph, fired at the
    # same moment: it must NOT be merged into the real incident.
    decoy = NormalizedEvent(
        event_id="evt-decoy",
        event_time=alerts[0].event_time + timedelta(seconds=1),
        ingestion_time=alerts[0].ingestion_time,
        source_type=SourceType.ALERT,
        event_type="ALERT",
        service_name="recommendation-service",
        severity=Severity.WARN,
        message="unrelated alert",
        attributes={"alertname": "DecoyAlert"},
    )

    result = correlate_events(events + [decoy])

    # All real-alert services are connected (gateway<->order<->payment), so the
    # fault's alerts form ONE incident; the decoy forms its own.
    real_groups = [
        inc for inc in result.alert_grouping.incidents if "recommendation-service" not in inc["services"]
    ]
    decoy_groups = [
        inc for inc in result.alert_grouping.incidents if "recommendation-service" in inc["services"]
    ]

    assert len(real_groups) == 1
    assert real_groups[0]["alert_count"] == len(alerts)
    assert set(real_groups[0]["services"]) <= {
        "api-gateway",
        "order-service",
        "payment-service",
    }
    assert len(decoy_groups) == 1
    assert result.alert_grouping.raw_alert_count == len(alerts) + 1
    assert result.alert_grouping.reduction_ratio == round((len(alerts) + 1) / 2, 2)
