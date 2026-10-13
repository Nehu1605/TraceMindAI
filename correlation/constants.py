"""Constants for the correlation layer: node types, edge types, weights.

The graph vocabulary follows the project data model (``Service``,
``TraceSpan``, ``LogEvent``, ``MetricAnomaly``, ``Deployment``, ``Commit``,
``Incident``) and the suggested edge types, narrowed to the subset this
phase actually produces.
"""

from __future__ import annotations

from enum import Enum

from ingestion.schema import EvidenceQuality


class NodeType(str, Enum):
    SERVICE = "Service"
    TRACE = "Trace"
    SPAN = "TraceSpan"
    LOG = "LogEvent"
    METRIC = "MetricSample"
    DEPLOYMENT = "Deployment"
    COMMIT = "Commit"
    ALERT = "Alert"
    INCIDENT = "Incident"


class EdgeType(str, Enum):
    PART_OF = "PART_OF"                 # span -> trace
    PARENT_OF = "PARENT_OF"             # parent span -> child span
    CALLS = "CALLS"                     # service -> downstream service
    GENERATED = "GENERATED"             # producer -> produced event
    OBSERVED_DURING = "OBSERVED_DURING"  # event -> service / time window
    DEPLOYED_TO = "DEPLOYED_TO"         # deployment -> service
    MODIFIED = "MODIFIED"               # deployment -> commit
    PRECEDED = "PRECEDED"               # event -> later event (temporal)
    GROUPED_INTO = "GROUPED_INTO"       # alert -> incident


# Confidence weight for each evidence-quality label. Correlation scoring in
# later phases multiplies edge weight by these values.
EVIDENCE_WEIGHTS: dict[EvidenceQuality, float] = {
    EvidenceQuality.DIRECT: 1.0,
    EvidenceQuality.INFERRED: 0.6,
    EvidenceQuality.TIME_ONLY: 0.3,
    EvidenceQuality.UNKNOWN: 0.0,
}

# Root service dependency seen in the demo (used only for documentation and
# for tests that need a known topology); the live graph is derived from spans.
KNOWN_SERVICE_CALLS: tuple[tuple[str, str], ...] = (
    ("api-gateway", "order-service"),
    ("order-service", "payment-service"),
    ("order-service", "user-service"),
    ("payment-service", "postgres"),
)


def service_node(name: str) -> str:
    return f"service:{name}"


def trace_node(trace_id: str) -> str:
    return f"trace:{trace_id}"


def span_node(span_id: str) -> str:
    return f"span:{span_id}"


def log_node(event_id: str) -> str:
    return f"log:{event_id}"


def metric_node(event_id: str) -> str:
    return f"metric:{event_id}"


def deployment_node(deployment_id: str) -> str:
    return f"deployment:{deployment_id}"


def commit_node(sha: str) -> str:
    return f"commit:{sha}"


def alert_node(event_id: str) -> str:
    return f"alert:{event_id}"


def incident_node(incident_id: str) -> str:
    return f"incident:{incident_id}"
