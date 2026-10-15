"""Data-quality reporting (improvement plan I6).

Summarizes what was ingested, what was quarantined and why, and how much the
data can be trusted: missing-trace-id rate, unknown-service rate, late-event
rate, suspected clock skew and broken trace links. These figures are exactly
what the "messy telemetry" degradation test reports on.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import median

from .schema import EvidenceQuality, NormalizedEvent, SourceType
from .validation import QuarantineRecord


@dataclass
class QualityReport:
    total_raw: int = 0
    valid_events: int = 0
    quarantined: int = 0
    by_source_type: dict[str, int] = field(default_factory=dict)
    quarantine_reasons: dict[str, int] = field(default_factory=dict)
    evidence_quality: dict[str, int] = field(default_factory=dict)
    missing_trace_id: int = 0
    missing_trace_id_rate: float = 0.0
    unknown_service: int = 0
    late_events: int = 0
    clock_skew_suspected: int = 0
    broken_trace_links: int = 0
    ingestion_lag_ms_p50: float | None = None
    ingestion_lag_ms_p95: float | None = None
    generated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "total_raw": self.total_raw,
            "valid_events": self.valid_events,
            "quarantined": self.quarantined,
            "quarantine_rate": round(
                self.quarantined / self.total_raw, 4
            )
            if self.total_raw
            else 0.0,
            "by_source_type": self.by_source_type,
            "quarantine_reasons": self.quarantine_reasons,
            "evidence_quality": self.evidence_quality,
            "missing_trace_id": self.missing_trace_id,
            "missing_trace_id_rate": round(self.missing_trace_id_rate, 4),
            "unknown_service": self.unknown_service,
            "late_events": self.late_events,
            "clock_skew_suspected": self.clock_skew_suspected,
            "broken_trace_links": self.broken_trace_links,
            "ingestion_lag_ms_p50": self.ingestion_lag_ms_p50,
            "ingestion_lag_ms_p95": self.ingestion_lag_ms_p95,
            "generated_at": self.generated_at,
        }


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = int(round(fraction * (len(ordered) - 1)))
    return ordered[index]


def build_quality_report(
    events: list[NormalizedEvent],
    quarantined: list[QuarantineRecord],
    total_raw: int | None = None,
) -> QualityReport:
    report = QualityReport(generated_at=datetime.now(tz=timezone.utc).isoformat())

    by_source: Counter[str] = Counter(e.source_type.value for e in events)
    by_quality: Counter[str] = Counter(e.evidence_quality.value for e in events)
    reasons: Counter[str] = Counter()
    for record in quarantined:
        for reason in record.reasons:
            reasons[reason] += 1

    trace_bearing = [e for e in events if e.source_type in (SourceType.TRACE, SourceType.LOG)]
    missing_trace = sum(1 for e in trace_bearing if not e.trace_id)

    lags = [(e.ingestion_time - e.event_time).total_seconds() * 1000.0 for e in events]
    lags = [lag for lag in lags if lag >= 0]

    report.total_raw = total_raw if total_raw is not None else len(events) + len(quarantined)
    report.valid_events = len(events)
    report.quarantined = len(quarantined)
    report.by_source_type = dict(by_source)
    report.quarantine_reasons = dict(reasons)
    report.evidence_quality = dict(by_quality)
    report.missing_trace_id = missing_trace
    report.missing_trace_id_rate = (
        missing_trace / len(trace_bearing) if trace_bearing else 0.0
    )
    report.unknown_service = reasons.get("unknown_service", 0)
    report.late_events = sum(1 for e in events if e.is_late)
    report.clock_skew_suspected = sum(1 for e in events if e.clock_skew_suspected)
    report.broken_trace_links = sum(
        1 for e in events if e.attributes.get("broken_trace_link")
    )
    report.ingestion_lag_ms_p50 = (
        round(median(lags), 2) if lags else None
    )
    p95 = _percentile(lags, 0.95)
    report.ingestion_lag_ms_p95 = round(p95, 2) if p95 is not None else None
    return report
