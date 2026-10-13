"""Unit tests for the event graph (Phase 3)."""

from __future__ import annotations

from ingestion.schema import EvidenceQuality

from correlation.constants import EdgeType, NodeType, service_node, span_node
from correlation.graph import EventGraph


def test_add_node_and_edge_records_weight():
    g = EventGraph()
    g.add_node(service_node("payment-service"), NodeType.SERVICE, name="payment-service")
    g.add_node(span_node("s1"), NodeType.SPAN, service="payment-service")
    g.add_edge(
        service_node("payment-service"),
        span_node("s1"),
        EdgeType.GENERATED,
        EvidenceQuality.DIRECT,
    )

    edge = g.graph[service_node("payment-service")][span_node("s1")][EdgeType.GENERATED.value]
    assert edge["weight"] == 1.0
    assert edge["evidence_quality"] == "direct"


def test_nodes_and_edges_of_type():
    g = EventGraph()
    g.add_node("service:payment-service", NodeType.SERVICE)
    g.add_node("span:s1", NodeType.SPAN)
    g.add_edge("service:payment-service", "span:s1", EdgeType.GENERATED, EvidenceQuality.DIRECT)

    assert g.nodes_of_type(NodeType.SERVICE) == ["service:payment-service"]
    assert g.edges_of_type(EdgeType.GENERATED) == [("service:payment-service", "span:s1")]


def test_increment_call_aggregates_counts():
    g = EventGraph()
    g.add_node("service:a", NodeType.SERVICE)
    g.add_node("service:b", NodeType.SERVICE)

    g.increment_call("service:a", "service:b")
    g.increment_call("service:a", "service:b")
    g.increment_call("service:a", "service:b")

    assert g.service_dependencies() == [("service:a", "service:b", 3)]
    assert g.number_of_edges() == 1


def test_stats_and_serialization(tmp_path):
    g = EventGraph()
    g.add_node("service:a", NodeType.SERVICE)
    g.add_node("service:b", NodeType.SERVICE)
    g.increment_call("service:a", "service:b")

    stats = g.stats()
    assert stats["nodes"] == 2
    assert stats["edges_by_type"]["CALLS"] == 1

    path = g.save(tmp_path / "graph.json")
    payload = path.read_text(encoding="utf-8")
    assert '"nodes"' in payload and '"edges"' in payload
    assert g.to_dict()["nodes_by_type"]["Service"] == 2
