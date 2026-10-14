"""Anomaly detection against per-service baselines (improvement I8).

Two signal families are detected:

* **Metric series** - numeric samples (``db_connections_in_use``, latency,
  5xx rate, CPU, memory) bucketed per ``(service, metric)`` and compared to
  that service's own rolling baseline.
* **Derived error series** - error-log counts and 5xx span counts bucketed per
  service over time, so a service that only exposes errors through logs/traces
  still becomes a candidate.

Each anomaly records its onset (a change point), its magnitude (a robust
z-score), the peak value and the evidence event ids that produced it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from common.config import Settings, get_settings
from ingestion.schema import NormalizedEvent, Severity, SourceType

from .baselines import RollingBaseline
from .change_point import detect_change_point

_ERROR_SEVERITIES = {Severity.ERROR, Severity.FATAL}


@dataclass
class Anomaly:
    service: str
    metric: str
    direction: str
    magnitude: float
    onset_time: datetime
    end_time: datetime
    observed_peak: float
    baseline_median: float
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "service": self.service,
            "metric": self.metric,
            "direction": self.direction,
            "magnitude": round(self.magnitude, 4),
            "onset_time": self.onset_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "observed_peak": round(self.observed_peak, 4),
            "baseline_median": round(self.baseline_median, 4),
            "evidence_ids": self.evidence_ids,
        }


@dataclass
class DetectionResult:
    anomalies: list[Anomaly] = field(default_factory=list)

    def by_service(self) -> dict[str, list[Anomaly]]:
        grouped: dict[str, list[Anomaly]] = defaultdict(list)
        for anomaly in self.anomalies:
            grouped[anomaly.service].append(anomaly)
        return dict(grouped)

    def onset_by_service(self) -> dict[str, datetime]:
        onsets: dict[str, datetime] = {}
        for anomaly in self.anomalies:
            current = onsets.get(anomaly.service)
            if current is None or anomaly.onset_time < current:
                onsets[anomaly.service] = anomaly.onset_time
        return onsets

    def to_dict(self) -> dict:
        return {
            "anomaly_count": len(self.anomalies),
            "services": sorted({a.service for a in self.anomalies}),
            "anomalies": [a.to_dict() for a in self.anomalies],
        }


def _series_anomaly(
    service: str,
    metric: str,
    points: list[tuple[datetime, float, str]],
    z_threshold: float,
    warmup: int,
) -> Anomaly | None:
    """Detect one anomaly in a ``(time, value, event_id)`` series."""

    if len(points) <= warmup:
        return None
    points = sorted(points, key=lambda p: p[0])
    values = [p[1] for p in points]

    change = detect_change_point(values, z_threshold=z_threshold, min_points=warmup)
    if change is None:
        return None

    baseline = RollingBaseline()
    baseline.extend(values[:warmup])
    peak_z = 0.0
    peak_value = values[change.index]
    evidence: list[str] = []
    end_index = change.index
    for index in range(change.index, len(points)):
        z = baseline.robust_z(values[index])
        if abs(z) >= z_threshold:
            end_index = index
            evidence.append(points[index][2])
            if abs(z) > abs(peak_z):
                peak_z = z
                peak_value = values[index]

    if not evidence:
        evidence = [points[change.index][2]]

    return Anomaly(
        service=service,
        metric=metric,
        direction=change.direction,
        magnitude=abs(peak_z),
        onset_time=points[change.index][0],
        end_time=points[end_index][0],
        observed_peak=peak_value,
        baseline_median=baseline.median,
        evidence_ids=evidence,
    )


class AnomalyDetector:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.z = self.settings.anomaly_z_threshold
        self.warmup = self.settings.baseline_warmup_points

    # -- metric series ----------------------------------------------------
    def _metric_anomalies(self, events: list[NormalizedEvent]) -> list[Anomaly]:
        series: dict[tuple[str, str], list[tuple[datetime, float, str]]] = defaultdict(list)
        for event in events:
            if event.source_type != SourceType.METRIC or event.metric_name is None:
                continue
            if event.metric_value is None or not event.service_name:
                continue
            series[(event.service_name, event.metric_name)].append(
                (event.event_time, float(event.metric_value), event.event_id)
            )

        anomalies: list[Anomaly] = []
        for (service, metric), points in series.items():
            anomaly = _series_anomaly(service, metric, points, self.z, self.warmup)
            if anomaly is not None:
                anomalies.append(anomaly)
        return anomalies

    # -- derived error series --------------------------------------------
    def _derived_series(
        self,
        error_events: list[NormalizedEvent],
        all_events: list[NormalizedEvent],
        bucket_seconds: float = 5.0,
    ) -> dict[str, list[tuple[datetime, float, str]]]:
        """Error counts per service on a *full* time grid.

        The grid is essential: without the leading zero-count buckets a series
        that only starts when errors begin looks flat, so no change point is
        found. Filling zeros back to the first observed event gives each
        service a healthy baseline to deviate from.
        """

        if not error_events or not all_events:
            return {}
        lo = _floor(min(e.event_time for e in all_events), bucket_seconds)
        hi = _floor(max(e.event_time for e in all_events), bucket_seconds)
        steps = int((hi - lo).total_seconds() // bucket_seconds) + 1

        buckets: dict[str, dict[datetime, list[str]]] = defaultdict(lambda: defaultdict(list))
        for event in error_events:
            if not event.service_name:
                continue
            buckets[event.service_name][_floor(event.event_time, bucket_seconds)].append(
                event.event_id
            )

        out: dict[str, list[tuple[datetime, float, str]]] = {}
        for service, by_time in buckets.items():
            points: list[tuple[datetime, float, str]] = []
            for step in range(steps):
                when = lo + timedelta(seconds=bucket_seconds * step)
                ids = by_time.get(when, [])
                points.append((when, float(len(ids)), ids[0] if ids else ""))
            out[service] = points
        return out

    def _derived_anomalies(self, events: list[NormalizedEvent]) -> list[Anomaly]:
        error_events = [
            e
            for e in events
            if (e.source_type == SourceType.LOG and e.severity in _ERROR_SEVERITIES)
            or (e.source_type == SourceType.TRACE and (e.status_code or 0) >= 500)
        ]
        anomalies: list[Anomaly] = []
        for service, points in self._derived_series(error_events, events).items():
            anomaly = _series_anomaly(service, "error_rate", points, self.z, self.warmup)
            if anomaly is not None:
                anomaly.evidence_ids = [eid for eid in anomaly.evidence_ids if eid]
                anomalies.append(anomaly)
        return anomalies

    def detect(self, events: list[NormalizedEvent]) -> DetectionResult:
        anomalies = self._metric_anomalies(events) + self._derived_anomalies(events)
        anomalies.sort(key=lambda a: (a.onset_time, a.service))
        return DetectionResult(anomalies=anomalies)


def _floor(when: datetime, seconds: float) -> datetime:
    epoch = when.timestamp()
    floored = epoch - (epoch % seconds)
    return when.fromtimestamp(floored, tz=when.tzinfo)
