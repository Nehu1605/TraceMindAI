"""Correlators: turn flat normalized events into typed graph links.

Two kinds of linking, matching the improvement plan's I6 requirement:

* **Direct** links use trace/span ids (a log with a valid trace context is
  attached to the exact span that produced it).
* **Fallback** links are used when the trace id is missing: match by service
  and time window, and require an *error signature* on both sides (an error
  severity on the log and a 5xx/error status on the span) before calling the
  link ``inferred``; when only service + time agree it is ``time_only``. The
  link is kept but its lower confidence travels with it, so downstream scoring
  can discount it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ingestion.schema import EvidenceQuality, NormalizedEvent, Severity, SourceType

from .constants import (
    EdgeType,
    NodeType,
    alert_node,
    commit_node,
    deployment_node,
    log_node,
    metric_node,
    service_node,
    span_node,
    trace_node,
)
from .graph import EventGraph

ERROR_SEVERITIES = {Severity.ERROR, Severity.FATAL}


def _is_error(event: NormalizedEvent) -> bool:
    return event.severity in ERROR_SEVERITIES


def _span_error(event: NormalizedEvent) -> bool:
    if _is_error(event):
        return True
    return event.status_code is not None and event.status_code >= 500


def _closest(
    candidates: list[NormalizedEvent], when: datetime
) -> NormalizedEvent | None:
    if not candidates:
        return None
    return min(candidates, key=lambda c: abs((c.event_time - when).total_seconds()))


class Correlators:
    def __init__(self, graph: EventGraph, window_seconds: float = 30.0) -> None:
        self.graph = graph
        self.window = timedelta(seconds=window_seconds)
        self.counts: dict[str, int] = {
            "direct": 0,
            "inferred": 0,
            "time_only": 0,
        }

    def _record(self, quality: EvidenceQuality) -> None:
        self.counts[quality.value] = self.counts.get(quality.value, 0) + 1

    def _link(
        self,
        src: str,
        dst: str,
        edge_type: EdgeType,
        quality: EvidenceQuality,
        **attrs,
    ) -> None:
        self.graph.add_edge(src, dst, edge_type, quality, **attrs)
        self._record(quality)

    # -- spans / services -------------------------------------------------
    def correlate_spans(self, events: list[NormalizedEvent]) -> None:
        spans = [e for e in events if e.source_type == SourceType.TRACE]
        span_ids = {e.span_id for e in spans if e.span_id}

        for span in spans:
            if not span.span_id:
                continue
            node = span_node(span.span_id)
            self.graph.add_node(
                node,
                NodeType.SPAN,
                label=span.message,
                service=span.service_name,
                severity=span.severity.value,
                event_time=span.event_time.isoformat(),
                duration_ms=span.duration_ms,
                status_code=span.status_code,
                evidence_id=span.event_id,
                source_reference=span.source_reference,
            )
            if span.trace_id:
                tr = trace_node(span.trace_id)
                if not self.graph.has_node(tr):
                    self.graph.add_node(tr, NodeType.TRACE, trace_id=span.trace_id)
                self._link(node, tr, EdgeType.PART_OF, EvidenceQuality.DIRECT)
            if span.service_name:
                svc = service_node(span.service_name)
                if not self.graph.has_node(svc):
                    self.graph.add_node(svc, NodeType.SERVICE, name=span.service_name)
                self._link(
                    svc, node, EdgeType.GENERATED, EvidenceQuality.DIRECT
                )

        # Parent/child and cross-service CALLS.
        for span in spans:
            if not span.parent_span_id or span.parent_span_id not in span_ids:
                continue
            parent = span_node(span.parent_span_id)
            child = span_node(span.span_id)
            self._link(parent, child, EdgeType.PARENT_OF, EvidenceQuality.DIRECT)
            parent_service = self.graph.graph.nodes[parent].get("service")
            child_service = self.graph.graph.nodes[child].get("service")
            if parent_service and child_service and parent_service != child_service:
                self.graph.increment_call(
                    service_node(parent_service), service_node(child_service)
                )
                self._record(EvidenceQuality.DIRECT)

        # Temporal ordering within each trace (PRECEDED).
        by_trace: dict[str, list[NormalizedEvent]] = {}
        for span in spans:
            if span.trace_id:
                by_trace.setdefault(span.trace_id, []).append(span)
        for trace_spans in by_trace.values():
            ordered = sorted(trace_spans, key=lambda e: e.event_time)
            for earlier, later in zip(ordered, ordered[1:]):
                self._link(
                    span_node(earlier.span_id),
                    span_node(later.span_id),
                    EdgeType.PRECEDED,
                    EvidenceQuality.DIRECT,
                )

    # -- logs -------------------------------------------------------------
    def correlate_logs(self, events: list[NormalizedEvent]) -> None:
        spans = [e for e in events if e.source_type == SourceType.TRACE and e.span_id]
        spans_by_trace: dict[str, list[NormalizedEvent]] = {}
        spans_by_service: dict[str, list[NormalizedEvent]] = {}
        for span in spans:
            if span.trace_id:
                spans_by_trace.setdefault(span.trace_id, []).append(span)
            if span.service_name:
                spans_by_service.setdefault(span.service_name, []).append(span)

        for log in events:
            if log.source_type != SourceType.LOG:
                continue
            node = log_node(log.event_id)
            self.graph.add_node(
                node,
                NodeType.LOG,
                label=(log.message or "")[:120],
                service=log.service_name,
                severity=log.severity.value,
                event_time=log.event_time.isoformat(),
                event_type=log.event_type,
                evidence_id=log.event_id,
                source_reference=log.source_reference,
            )
            if log.service_name:
                svc = service_node(log.service_name)
                if not self.graph.has_node(svc):
                    self.graph.add_node(svc, NodeType.SERVICE, name=log.service_name)

            target, quality = self._match_log(log, spans_by_trace, spans_by_service)
            if target is not None:
                self._link(target, node, EdgeType.GENERATED, quality)
            elif log.service_name:
                # No span to attach to: keep the log tied to its service only.
                self._link(
                    service_node(log.service_name),
                    node,
                    EdgeType.GENERATED,
                    EvidenceQuality.TIME_ONLY,
                )

    def _match_log(
        self,
        log: NormalizedEvent,
        spans_by_trace: dict[str, list[NormalizedEvent]],
        spans_by_service: dict[str, list[NormalizedEvent]],
    ) -> tuple[str | None, EvidenceQuality]:
        # 1. Direct: same trace id (prefer the error span, else the closest).
        if log.trace_id:
            trace_spans = spans_by_trace.get(log.trace_id)
            if trace_spans:
                candidates = [s for s in trace_spans if _span_error(s)] or trace_spans
                match = _closest(candidates, log.event_time)
                if match is not None:
                    return span_node(match.span_id), EvidenceQuality.DIRECT

        # 2. Inferred: same service, within window, error signature on both
        #    sides (error log + 5xx/error span).
        if log.service_name and _is_error(log):
            candidates = [
                s
                for s in spans_by_service.get(log.service_name, [])
                if _span_error(s) and abs((s.event_time - log.event_time) <= self.window)
            ]
            match = _closest(candidates, log.event_time)
            if match is not None:
                return span_node(match.span_id), EvidenceQuality.INFERRED

        # 3. Time-only: same service, within window, no signature agreement.
        if log.service_name:
            candidates = [
                s
                for s in spans_by_service.get(log.service_name, [])
                if abs((s.event_time - log.event_time) <= self.window)
            ]
            match = _closest(candidates, log.event_time)
            if match is not None:
                return span_node(match.span_id), EvidenceQuality.TIME_ONLY

        return None, EvidenceQuality.UNKNOWN

    # -- metrics ----------------------------------------------------------
    def correlate_metrics(self, events: list[NormalizedEvent]) -> None:
        for metric in events:
            if metric.source_type != SourceType.METRIC:
                continue
            node = metric_node(metric.event_id)
            self.graph.add_node(
                node,
                NodeType.METRIC,
                metric_name=metric.metric_name,
                value=metric.metric_value,
                service=metric.service_name,
                event_time=metric.event_time.isoformat(),
                evidence_id=metric.event_id,
                source_reference=metric.source_reference,
            )
            if metric.service_name:
                svc = service_node(metric.service_name)
                if not self.graph.has_node(svc):
                    self.graph.add_node(svc, NodeType.SERVICE, name=metric.service_name)
                self._link(
                    svc, node, EdgeType.GENERATED, EvidenceQuality.TIME_ONLY
                )

    # -- deployments ------------------------------------------------------
    def correlate_deployments(self, events: list[NormalizedEvent]) -> None:
        for deployment in events:
            if deployment.source_type != SourceType.DEPLOYMENT:
                continue
            node = deployment_node(deployment.deployment_id or deployment.event_id)
            self.graph.add_node(
                node,
                NodeType.DEPLOYMENT,
                service=deployment.service_name,
                event_time=deployment.event_time.isoformat(),
                message=deployment.message,
                evidence_id=deployment.event_id,
                source_reference=deployment.source_reference,
            )
            if deployment.service_name:
                svc = service_node(deployment.service_name)
                if not self.graph.has_node(svc):
                    self.graph.add_node(svc, NodeType.SERVICE, name=deployment.service_name)
                self._link(
                    node, svc, EdgeType.DEPLOYED_TO, EvidenceQuality.TIME_ONLY
                )
            commit = deployment.attributes.get("commit_sha")
            if commit:
                cnode = commit_node(str(commit))
                if not self.graph.has_node(cnode):
                    self.graph.add_node(cnode, NodeType.COMMIT, sha=str(commit))
                self._link(node, cnode, EdgeType.MODIFIED, EvidenceQuality.DIRECT)

    # -- alerts -----------------------------------------------------------
    def correlate_alerts(self, events: list[NormalizedEvent]) -> None:
        for alert in events:
            if alert.source_type != SourceType.ALERT:
                continue
            node = alert_node(alert.event_id)
            self.graph.add_node(
                node,
                NodeType.ALERT,
                alertname=alert.attributes.get("alertname"),
                service=alert.service_name,
                severity=alert.severity.value,
                event_time=alert.event_time.isoformat(),
                message=alert.message,
                evidence_id=alert.event_id,
                source_reference=alert.source_reference,
            )
            if alert.service_name:
                svc = service_node(alert.service_name)
                if not self.graph.has_node(svc):
                    self.graph.add_node(svc, NodeType.SERVICE, name=alert.service_name)
                self._link(
                    node, svc, EdgeType.OBSERVED_DURING, EvidenceQuality.TIME_ONLY
                )
