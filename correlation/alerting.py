"""Alert grouping (improvement I10, correlation half).

Raw alerts are collapsed into incidents when they fall inside the same time
window *and* their services are connected in the service graph. This is the
"Splunk ITSI episode"-style reduction the plan asks for: the alert-reduction
ratio (raw alerts / incident groups) is the headline number, and the incident
becomes a first-class node other phases can attach evidence to.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import timedelta

import networkx as nx

from ingestion.schema import NormalizedEvent, Severity, SourceType

from .constants import EdgeType, NodeType, incident_node, service_node
from .graph import EventGraph

_SEVERITY_RANK = {
    Severity.TRACE: 0,
    Severity.DEBUG: 1,
    Severity.INFO: 2,
    Severity.WARN: 3,
    Severity.ERROR: 4,
    Severity.FATAL: 5,
    Severity.UNKNOWN: -1,
}


@dataclass
class AlertGroupingResult:
    incidents: list[dict] = field(default_factory=list)
    raw_alert_count: int = 0

    @property
    def incident_count(self) -> int:
        return len(self.incidents)

    @property
    def reduction_ratio(self) -> float:
        if not self.incidents:
            return 0.0
        return round(self.raw_alert_count / len(self.incidents), 2)

    def to_dict(self) -> dict:
        return {
            "raw_alert_count": self.raw_alert_count,
            "incident_count": self.incident_count,
            "alert_reduction_ratio": self.reduction_ratio,
            "incidents": self.incidents,
        }


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _service_adjacency(graph: EventGraph) -> nx.Graph:
    """Undirected service connectivity derived from CALLS edges.

    Nodes are keyed by *raw* service name (``payment-service``), matching the
    values carried on alerts, not by graph node id (``service:payment-service``).
    """

    adj = nx.Graph()
    for u, v, _count in graph.service_dependencies():
        adj.add_edge(u.removeprefix("service:"), v.removeprefix("service:"))
    return adj


def _hops(adj: nx.Graph, a: str | None, b: str | None) -> int | None:
    if a is None or b is None:
        return None
    if a == b:
        return 0
    if a in adj and b in adj and nx.has_path(adj, a, b):
        return nx.shortest_path_length(adj, a, b)
    return None


def group_alerts(
    alerts: list[NormalizedEvent],
    graph: EventGraph,
    window_seconds: float = 300.0,
    max_hops: int = 2,
) -> AlertGroupingResult:
    alerts = [a for a in alerts if a.source_type == SourceType.ALERT]
    result = AlertGroupingResult(raw_alert_count=len(alerts))
    if not alerts:
        return result

    adj = _service_adjacency(graph)
    window = timedelta(seconds=window_seconds)
    uf = _UnionFind(len(alerts))

    services = [a.service_name for a in alerts]
    for i in range(len(alerts)):
        for j in range(i + 1, len(alerts)):
            if abs((alerts[i].event_time - alerts[j].event_time)) > window:
                continue
            hops = _hops(adj, services[i], services[j])
            if hops is not None and hops <= max_hops:
                uf.union(i, j)

    clusters: dict[int, list[NormalizedEvent]] = {}
    for index, alert in enumerate(alerts):
        clusters.setdefault(uf.find(index), []).append(alert)

    for cluster in clusters.values():
        cluster.sort(key=lambda a: a.event_time)
        incident = _build_incident(cluster)
        result.incidents.append(incident)
        _attach_incident(graph, incident)

    result.incidents.sort(key=lambda inc: inc["start_time"])
    return result


def _build_incident(cluster: list[NormalizedEvent]) -> dict:
    evidence_ids = sorted(a.event_id for a in cluster)
    incident_id = "inc-" + hashlib.sha1("|".join(evidence_ids).encode()).hexdigest()[:12]
    services = sorted({a.service_name for a in cluster if a.service_name})
    worst = max(cluster, key=lambda a: _SEVERITY_RANK.get(a.severity, -1))
    return {
        "incident_id": incident_id,
        "start_time": cluster[0].event_time.isoformat(),
        "end_time": cluster[-1].event_time.isoformat(),
        "services": services,
        "alert_count": len(cluster),
        "severity": worst.severity.value,
        "alertnames": sorted(
            {str(a.attributes.get("alertname")) for a in cluster if a.attributes.get("alertname")}
        ),
        "evidence_ids": evidence_ids,
    }


def _attach_incident(graph: EventGraph, incident: dict) -> None:
    node = incident_node(incident["incident_id"])
    graph.add_node(
        node,
        NodeType.INCIDENT,
        services=incident["services"],
        severity=incident["severity"],
        alert_count=incident["alert_count"],
        start_time=incident["start_time"],
        end_time=incident["end_time"],
    )
    for evidence_id in incident["evidence_ids"]:
        alert = f"alert:{evidence_id}"
        if graph.has_node(alert):
            graph.add_edge(
                alert,
                node,
                EdgeType.GROUPED_INTO,
                # grouping is time+topology based, never a direct trace link
                _time_only(),
            )
    # Also connect the incident to each affected service for topology queries.
    for service in incident["services"]:
        svc = service_node(service)
        if graph.has_node(svc):
            graph.add_edge(node, svc, EdgeType.OBSERVED_DURING, _time_only())


def _time_only():
    from ingestion.schema import EvidenceQuality

    return EvidenceQuality.TIME_ONLY
