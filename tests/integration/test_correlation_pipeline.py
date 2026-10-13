"""Integration test: ingest a generated dataset, then correlate it."""

from __future__ import annotations

from ingestion.pipeline import run_ingestion
from ingestion.schema import SourceType
from simulator.generate_telemetry import DEGRADE_PRESETS, generate_dataset

from correlation.builder import correlate_events
from correlation.constants import EdgeType, service_node


def _events(tmp_path, degrade="none", seed=21):
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    generate_dataset(raw, seed=seed, requests=40, degrade=DEGRADE_PRESETS[degrade])
    return run_ingestion(raw, out).events


def test_clean_dataset_builds_expected_graph(tmp_path):
    events = _events(tmp_path)
    result = correlate_events(events)

    for service in ("api-gateway", "order-service", "payment-service", "user-service"):
        assert result.graph.has_node(service_node(service))

    for edge_type in (
        EdgeType.PART_OF,
        EdgeType.PARENT_OF,
        EdgeType.CALLS,
        EdgeType.GENERATED,
        EdgeType.DEPLOYED_TO,
        EdgeType.MODIFIED,
        EdgeType.OBSERVED_DURING,
    ):
        assert result.graph.edges_of_type(edge_type), edge_type

    deps = {u for u, _v, _c in result.graph.service_dependencies()}
    assert service_node("api-gateway") in deps


def test_clean_dataset_groups_all_alerts_into_one_incident(tmp_path):
    events = _events(tmp_path)
    result = correlate_events(events)

    assert result.alert_grouping.raw_alert_count >= 1
    assert result.alert_grouping.incident_count == 1
    assert result.alert_grouping.reduction_ratio >= 2.0


def test_messy_dataset_produces_inferred_fallback_links(tmp_path):
    events = _events(tmp_path, degrade="heavy", seed=22)
    result = correlate_events(events)

    counts = result.correlation_counts
    assert counts.get("direct", 0) > 0
    # Missing trace ids in the messy data must still be linked, just with
    # lower confidence (I6 fallback matching).
    assert counts.get("inferred", 0) + counts.get("time_only", 0) > 0
