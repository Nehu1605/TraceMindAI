"""Correlation orchestration: normalized events in, evidence graph out."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from common.config import Settings, get_settings
from ingestion.schema import NormalizedEvent, SourceType

from .alerting import AlertGroupingResult, group_alerts
from .correlators import Correlators
from .graph import EventGraph


@dataclass
class CorrelationResult:
    graph: EventGraph
    alert_grouping: AlertGroupingResult
    correlation_counts: dict[str, int] = field(default_factory=dict)
    graph_stats: dict[str, Any] = field(default_factory=dict)
    event_count: int = 0

    def summary(self) -> dict[str, Any]:
        return {
            "event_count": self.event_count,
            "correlation_counts": self.correlation_counts,
            "graph": self.graph_stats,
            "alert_grouping": self.alert_grouping.to_dict(),
        }


def correlate_events(
    events: list[NormalizedEvent],
    settings: Settings | None = None,
) -> CorrelationResult:
    settings = settings or get_settings()
    graph = EventGraph()
    correlators = Correlators(graph, window_seconds=settings.correlation_window_seconds)

    correlators.correlate_spans(events)
    correlators.correlate_logs(events)
    correlators.correlate_metrics(events)
    correlators.correlate_deployments(events)
    correlators.correlate_alerts(events)

    alerts = [e for e in events if e.source_type == SourceType.ALERT]
    grouping = group_alerts(
        alerts,
        graph,
        window_seconds=settings.alert_group_window_seconds,
        max_hops=settings.alert_group_max_hops,
    )

    return CorrelationResult(
        graph=graph,
        alert_grouping=grouping,
        correlation_counts=dict(correlators.counts),
        graph_stats=graph.stats(),
        event_count=len(events),
    )
