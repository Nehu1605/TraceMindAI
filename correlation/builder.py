"""Correlation orchestration: normalized events in, evidence graph out."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from common.config import Settings, get_settings
from ingestion.schema import NormalizedEvent, SourceType

from .alerting import AlertGroupingResult, group_alerts
from .correlators import Correlators
from .graph import EventGraph
from .log_reduction import LogReductionResult, reduce_logs, windows_from_incidents


@dataclass
class CorrelationResult:
    graph: EventGraph
    alert_grouping: AlertGroupingResult
    log_reduction: LogReductionResult
    correlation_counts: dict[str, int] = field(default_factory=dict)
    graph_stats: dict[str, Any] = field(default_factory=dict)
    event_count: int = 0

    def summary(self) -> dict[str, Any]:
        return {
            "event_count": self.event_count,
            "correlation_counts": self.correlation_counts,
            "graph": self.graph_stats,
            "alert_grouping": self.alert_grouping.to_dict(),
            "log_reduction": self.log_reduction.to_dict(),
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

    # I10 (log cost): keep full logs only around incidents, sample the rest,
    # and report bytes retained against bytes ingested.
    windows = windows_from_incidents(
        grouping.incidents, pad_seconds=settings.log_incident_pad_seconds
    )
    log_reduction = reduce_logs(
        events, keep_windows=windows, sample_rate=settings.log_sample_rate
    )

    return CorrelationResult(
        graph=graph,
        alert_grouping=grouping,
        log_reduction=log_reduction,
        correlation_counts=dict(correlators.counts),
        graph_stats=graph.stats(),
        event_count=len(events),
    )
