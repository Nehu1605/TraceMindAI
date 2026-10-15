"""The event/causality graph.

A thin, serializable wrapper around a NetworkX ``MultiDiGraph``. Nodes are
typed telemetry entities; edges are typed, *directed* evidence links, each
carrying an evidence-quality label and a numeric weight so later phases can
reason about how strongly two entities are connected.

The graph intentionally stores compact node/edge payloads (identifiers plus a
few key fields), not the whole event, so it stays inspectable and easy to
serialize for the dashboard.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx

from ingestion.schema import EvidenceQuality

from .constants import EVIDENCE_WEIGHTS, EdgeType, NodeType


class EventGraph:
    def __init__(self) -> None:
        self._g = nx.MultiDiGraph()

    # -- construction ----------------------------------------------------
    def add_node(
        self, node_id: str, node_type: NodeType, **attrs: Any
    ) -> None:
        self._g.add_node(node_id, node_type=node_type.value, **attrs)

    def add_edge(
        self,
        src: str,
        dst: str,
        edge_type: EdgeType,
        evidence_quality: EvidenceQuality = EvidenceQuality.UNKNOWN,
        **attrs: Any,
    ) -> None:
        self._g.add_edge(
            src,
            dst,
            key=edge_type.value,
            edge_type=edge_type.value,
            evidence_quality=evidence_quality.value,
            weight=EVIDENCE_WEIGHTS.get(evidence_quality, 0.0),
            **attrs,
        )

    # -- queries ---------------------------------------------------------
    @property
    def graph(self) -> nx.MultiDiGraph:
        return self._g

    def number_of_nodes(self) -> int:
        return self._g.number_of_nodes()

    def number_of_edges(self) -> int:
        return self._g.number_of_edges()

    def has_node(self, node_id: str) -> bool:
        return self._g.has_node(node_id)

    def nodes_of_type(self, node_type: NodeType) -> list[str]:
        return [
            n
            for n, data in self._g.nodes(data=True)
            if data.get("node_type") == node_type.value
        ]

    def edges_of_type(self, edge_type: EdgeType) -> list[tuple[str, str]]:
        return [
            (u, v)
            for u, v, data in self._g.edges(data=True)
            if data.get("edge_type") == edge_type.value
        ]

    def service_dependencies(self) -> list[tuple[str, str, int]]:
        """Aggregated service -> service CALLS counts.

        A single CALLS edge per service pair is kept, with an incrementing
        ``count`` attribute, so the graph stays compact while the number of
        observed cross-service calls is preserved.
        """

        deps: list[tuple[str, str, int]] = []
        for u, v, data in self._g.edges(data=True):
            if data.get("edge_type") == EdgeType.CALLS.value:
                deps.append((u, v, int(data.get("count", 1))))
        return sorted(deps)

    def increment_call(self, src: str, dst: str) -> None:
        """Increment the CALLS count between two services."""

        key = EdgeType.CALLS.value
        if self._g.has_edge(src, dst, key):
            self._g[src][dst][key]["count"] = (
                int(self._g[src][dst][key].get("count", 1)) + 1
            )
        else:
            self.add_edge(src, dst, EdgeType.CALLS)
            self._g[src][dst][key]["count"] = 1

    def connected_components(self) -> int:
        return nx.number_weakly_connected_components(self._g)

    def stats(self) -> dict[str, Any]:
        nodes_by_type: dict[str, int] = {}
        for _, data in self._g.nodes(data=True):
            key = data.get("node_type", "Unknown")
            nodes_by_type[key] = nodes_by_type.get(key, 0) + 1

        edges_by_type: dict[str, int] = {}
        for _, _, data in self._g.edges(data=True):
            key = data.get("edge_type", "Unknown")
            edges_by_type[key] = edges_by_type.get(key, 0) + 1

        return {
            "nodes": self.number_of_nodes(),
            "edges": self.number_of_edges(),
            "nodes_by_type": nodes_by_type,
            "edges_by_type": edges_by_type,
            "service_dependencies": [
                {"from": u, "to": v, "count": count}
                for u, v, count in self.service_dependencies()
            ],
            "connected_components": self.connected_components()
            if self.number_of_nodes()
            else 0,
        }

    # -- serialization ---------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        nodes = [
            {"id": node_id, **data} for node_id, data in self._g.nodes(data=True)
        ]
        edges = [
            {"source": u, "target": v, **data}
            for u, v, data in self._g.edges(data=True)
        ]
        return {"nodes": nodes, "edges": edges, **self.stats()}

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, default=str), encoding="utf-8")
        return path
