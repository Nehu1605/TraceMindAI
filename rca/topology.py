"""Service dependency topology for RCA (Phase 5, improvement I2).

Root-cause analysis needs to know who talks to whom. This rebuilds the
service-to-service call graph from parent/child spans (the strongest evidence)
and falls back to the documented demo topology when a dataset has no
cross-service spans.

An edge ``A -> B`` means "A calls B"; edge weight is the observed call count,
which later ranking turns into a path-confidence.
"""

from __future__ import annotations

import networkx as nx

from correlation.constants import KNOWN_SERVICE_CALLS
from ingestion.schema import NormalizedEvent, SourceType


def build_service_graph(events: list[NormalizedEvent]) -> nx.DiGraph:
    spans: dict[str, tuple[str | None, str | None]] = {}
    for event in events:
        if event.source_type == SourceType.TRACE and event.span_id:
            spans[event.span_id] = (event.service_name, event.parent_span_id)

    graph = nx.DiGraph()
    for service, parent_id in spans.values():
        if not service:
            continue
        graph.add_node(service)
        if parent_id and parent_id in spans:
            parent_service = spans[parent_id][0]
            if parent_service and parent_service != service:
                if graph.has_edge(parent_service, service):
                    graph[parent_service][service]["count"] += 1
                else:
                    graph.add_edge(parent_service, service, count=1)

    # Keep only the service nodes; a graph with no cross-service edges is
    # useless, so fall back to the documented topology.
    if not any(graph[u][v].get("count", 0) for u, v in graph.edges):
        graph = fallback_graph()
    return graph


def fallback_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    for src, dst in KNOWN_SERVICE_CALLS:
        graph.add_edge(src, dst, count=1)
    return graph


def service_nodes(graph: nx.DiGraph) -> list[str]:
    return list(graph.nodes())


def path_confidence(graph: nx.DiGraph, src: str, dst: str) -> float:
    """Confidence that a fault in ``dst`` explains symptoms in ``src``.

    Walks ``src -> dst`` in the call graph; each hop multiplies by a factor
    that shrinks with depth so a direct caller/callee link outweighs a long
    chain. Returns 0.0 when no path exists.
    """

    if src == dst or not nx.has_path(graph, src, dst):
        return 0.0
    try:
        path = nx.shortest_path(graph, src, dst)
    except nx.NetworkXNoPath:  # pragma: no cover - guarded by has_path
        return 0.0
    hops = len(path) - 1
    return 0.7 ** hops
