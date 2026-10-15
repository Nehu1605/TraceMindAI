"""Naive RCA baselines for comparison (Phase 5, improvement I2).

These are the straw men the propagation-aware engine has to beat:

* **B1 latest_anomaly** - whichever service alerted last.
* **B2 max_magnitude** - whichever service has the single largest anomaly.
* **B3 log_volume** - whichever service emitted the most error logs.
* **B4 latest_deploy** - "it was the last deployment" (any service).

Each returns a ranked list of service names so the Phase 7 evaluation can score
top-1 / top-3 accuracy identically for every method.
"""

from __future__ import annotations

from ingestion.schema import NormalizedEvent

from .commits import latest_deployment


def b1_latest_anomaly(anomalies: list, deployments: list[NormalizedEvent]) -> list[str]:
    onsets: dict[str, float] = {}
    for anomaly in anomalies:
        ts = anomaly.onset_time.timestamp()
        onsets[anomaly.service] = max(onsets.get(anomaly.service, float("-inf")), ts)
    return [s for s, _ in sorted(onsets.items(), key=lambda kv: kv[1], reverse=True)]


def b2_max_magnitude(anomalies: list, deployments: list[NormalizedEvent]) -> list[str]:
    peaks: dict[str, float] = {}
    for anomaly in anomalies:
        peaks[anomaly.service] = max(peaks.get(anomaly.service, 0.0), anomaly.magnitude)
    return [s for s, _ in sorted(peaks.items(), key=lambda kv: kv[1], reverse=True)]


def b3_log_volume(
    anomalies: list, deployments: list[NormalizedEvent], error_log_counts: dict[str, int] | None = None
) -> list[str]:
    counts = error_log_counts or {}
    services = {a.service for a in anomalies}
    return [s for s, _ in sorted(((s, counts.get(s, 0)) for s in services), key=lambda kv: kv[1], reverse=True)]


def b4_latest_deploy(anomalies: list, deployments: list[NormalizedEvent]) -> list[str]:
    if not anomalies:
        return []
    earliest = min(a.onset_time for a in anomalies)
    match = latest_deployment(earliest, deployments)
    if match is None:
        return []
    others = sorted({a.service for a in anomalies} - {match.service})
    return [match.service, *others]
