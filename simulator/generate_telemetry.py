"""Generate a synthetic telemetry dataset for the Phase 2 pipeline.

Produces the raw files the ingestion pipeline expects - ``traces.jsonl``,
``logs.jsonl``, ``metrics.csv``, ``deployments.csv`` and ``alerts.json`` -
for a reproducible incident, and can deliberately plant data-quality
problems to exercise the robustness work from the improvement plan (I6):

    missing trace ids, dropped spans, clock skew, duplicate records,
    invalid timestamps, out-of-range values, unknown service names,
    late-arriving events and broken trace links.

Usage::

    python -m simulator.generate_telemetry --out-dir data/synthetic/incident-001
    python -m simulator.generate_telemetry --degrade heavy --seed 7
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_TIME = datetime(2026, 10, 11, 10, 0, 0, tzinfo=timezone.utc)
INC_DEPLOY_COMMIT = "c0ffee1d00m3"
DECOY_DEPLOY_COMMIT = "dec0y0abc"
POOL_SIZE = 5


@dataclass
class DegradeConfig:
    missing_trace_id_rate: float = 0.0
    drop_span_rate: float = 0.0
    clock_skew_ms: int = 0
    skew_service: str = "payment-service"
    duplicate_rate: float = 0.0
    invalid_timestamp_count: int = 0
    out_of_range_count: int = 0
    unknown_service_count: int = 0
    late_event_count: int = 0
    broken_link_count: int = 0


DEGRADE_PRESETS: dict[str, DegradeConfig] = {
    "none": DegradeConfig(),
    "light": DegradeConfig(
        missing_trace_id_rate=0.10,
        drop_span_rate=0.10,
        clock_skew_ms=600,
        duplicate_rate=0.02,
        invalid_timestamp_count=1,
        out_of_range_count=1,
        unknown_service_count=1,
        late_event_count=1,
        broken_link_count=1,
    ),
    "heavy": DegradeConfig(
        missing_trace_id_rate=0.20,
        drop_span_rate=0.30,
        clock_skew_ms=700,
        duplicate_rate=0.05,
        invalid_timestamp_count=2,
        out_of_range_count=2,
        unknown_service_count=2,
        late_event_count=2,
        broken_link_count=1,
    ),
}


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _lag(rng: random.Random, service: str, start: datetime, degrade: DegradeConfig) -> datetime:
    if service == degrade.skew_service and degrade.clock_skew_ms:
        # Ingestion timestamp is *before* the event: event_time - ingestion_time = skew.
        return start - timedelta(milliseconds=degrade.clock_skew_ms)
    return start + timedelta(milliseconds=rng.randint(5, 40))


class DatasetBuilder:
    def __init__(self, degrade: DegradeConfig, seed: int, requests: int) -> None:
        self.degrade = degrade
        self.rng = random.Random(seed)
        self.requests = requests
        self.spans: list[dict] = []
        self.logs: list[dict] = []
        self.metrics: list[dict] = []
        self.alerts: list[dict] = []
        self.deployments: list[dict] = []
        self.challenges: list[dict] = []

    # -- helpers ---------------------------------------------------------
    def _record_challenge(self, kind: str, reference: str, description: str) -> None:
        self.challenges.append(
            {"challenge_type": kind, "source_reference": reference, "description": description}
        )

    def _maybe_drop_trace_id(self, log: dict) -> None:
        if self.degrade.missing_trace_id_rate and self.rng.random() < self.degrade.missing_trace_id_rate:
            log.pop("trace_id", None)
            log.pop("span_id", None)

    def _add_span(
        self,
        trace_id: str,
        span_id: str,
        parent: str | None,
        service: str,
        name: str,
        start: datetime,
        duration_ms: float,
        status: int,
        kind: str = "SERVER",
    ) -> None:
        if self.degrade.drop_span_rate and self.rng.random() < self.degrade.drop_span_rate:
            self._record_challenge("dropped_span", f"{trace_id}/{span_id}", "span sampled out")
            return
        end = start + timedelta(milliseconds=duration_ms)
        self.spans.append(
            {
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent,
                "service_name": service,
                "name": name,
                "kind": kind,
                "start_time": _iso(start),
                "end_time": _iso(end),
                "duration_ms": round(duration_ms, 3),
                "status_code": status,
                "ingestion_time": _iso(_lag(self.rng, service, start, self.degrade)),
            }
        )

    def _add_log(
        self,
        when: datetime,
        service: str,
        severity: str,
        message: str,
        event_type: str | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
    ) -> None:
        entry = {
            "timestamp": _iso(when),
            "service_name": service,
            "severity": severity,
            "message": message,
            "trace_id": trace_id,
            "span_id": span_id,
            "event_type": event_type or "LOG",
            "ingestion_time": _iso(_lag(self.rng, service, when, self.degrade)),
        }
        self._maybe_drop_trace_id(entry)
        self.logs.append(entry)

    # -- scenario --------------------------------------------------------
    def build(self) -> None:
        warmup = int(self.requests * 0.4)
        incident = int(self.requests * 0.4)
        incident_start = warmup
        incident_end = warmup + incident

        for i in range(self.requests):
            t0 = BASE_TIME + timedelta(milliseconds=500 * i)
            failing = incident_start <= i < incident_end
            trace_id = f"trace-{i:04d}"
            user_id = self.rng.choice(["user-1", "user-2", "user-3"])

            self._emit_request(t0, trace_id, user_id, failing)

        self._emit_metrics(warmup, incident_start, incident_end)
        self._emit_deployments(incident_start)
        self._emit_alerts(incident_start, incident_end)
        self._plant_corruption()

    def _emit_request(self, t0: datetime, trace_id: str, user_id: str, failing: bool) -> None:
        g = f"g-{trace_id}"
        o = f"o-{trace_id}"
        u = f"u-{trace_id}"
        p = f"p-{trace_id}"
        d = f"d-{trace_id}"

        self._add_span(trace_id, g, None, "api-gateway", "POST /orders", t0, 18 if not failing else 2100, 200 if not failing else 500)
        self._add_span(trace_id, o, g, "order-service", "POST /orders", t0 + timedelta(milliseconds=3), 12 if not failing else 2050, 200 if not failing else 502)
        self._add_span(trace_id, u, o, "user-service", f"GET /users/{user_id}", t0 + timedelta(milliseconds=5), 4, 200)
        self._add_span(trace_id, p, o, "payment-service", "POST /pay", t0 + timedelta(milliseconds=8), 6 if not failing else 2000, 200 if not failing else 503)
        self._add_span(trace_id, d, p, "postgres", "INSERT payment", t0 + timedelta(milliseconds=10), 2 if not failing else 1900, 200 if not failing else 504)

        order = trace_id.replace("trace-", "ORD-")
        if failing:
            self._add_log(t0 + timedelta(milliseconds=2000), "payment-service", "ERROR", f"Database connection acquisition timeout after 2000ms pool=10/10 order={order}", "DB_CONNECTION_TIMEOUT", trace_id, p)
            self._add_log(t0 + timedelta(milliseconds=2050), "order-service", "ERROR", f"payment-service returned 503 order={order} attempt=1", "HTTP_5XX", trace_id, o)
            self._add_log(t0 + timedelta(milliseconds=2100), "api-gateway", "ERROR", f"order-service returned 502 order={order} path=/checkout", "HTTP_5XX", trace_id, g)
        else:
            self._add_log(t0 + timedelta(milliseconds=8), "payment-service", "INFO", f"Payment approved order={order} amount=49.99 status=200", "LOG", trace_id, p)
            self._add_log(t0 + timedelta(milliseconds=15), "api-gateway", "INFO", f"Request served order={order} method=POST path=/checkout status=200 latency=18ms", "LOG", trace_id, g)

    def _emit_metrics(self, warmup: int, incident_start: int, incident_end: int) -> None:
        for i in range(0, self.requests, 4):
            when = BASE_TIME + timedelta(milliseconds=500 * i)
            failing = incident_start <= i < incident_end
            pool = POOL_SIZE if failing else 1
            self._metric(when, "payment-service", "db_connections_in_use", pool)
            self._metric(when, "payment-service", "http_request_duration_ms", 8 if not failing else 2000)
            self._metric(when, "payment-service", "http_5xx_rate", 0.0 if not failing else 1.0)
            self._metric(when, "api-gateway", "http_5xx_rate", 0.0 if not failing else 0.6)
            self._metric(when, "order-service", "cpu_percent", 20 + self.rng.random() * 10)
            self._metric(when, "user-service", "memory_percent", 35 + self.rng.random() * 5)

    def _metric(self, when: datetime, service: str, name: str, value: float) -> None:
        self.metrics.append(
            {
                "timestamp": _iso(when),
                "service_name": service,
                "metric_name": name,
                "value": value,
                "ingestion_time": _iso(_lag(self.rng, service, when, self.degrade)),
            }
        )

    def _emit_deployments(self, incident_start: int) -> None:
        self.deployments.append(
            {
                "deployment_id": "dep-baseline0001",
                "service_name": "payment-service",
                "timestamp": _iso(BASE_TIME - timedelta(minutes=30)),
                "commit_sha": "a1b2c3d",
                "status": "deployed",
                "changed_files": "services/payment_service/app.py",
                "change_summary": "Baseline payment service revision",
                "ingestion_time": _iso(BASE_TIME - timedelta(minutes=30) + timedelta(seconds=2)),
            }
        )
        onset = BASE_TIME + timedelta(milliseconds=500 * incident_start - 1000)
        self.deployments.append(
            {
                "deployment_id": "dep-incident0001",
                "service_name": "payment-service",
                "timestamp": _iso(onset),
                "commit_sha": INC_DEPLOY_COMMIT,
                "status": "deployed",
                "changed_files": "services/payment_service/app.py",
                "change_summary": "Introduce connection handling defect in payment-service",
                "ingestion_time": _iso(onset + timedelta(seconds=2)),
            }
        )
        # Decoy deployment (I1): an unrelated, *later* deploy on a service that
        # is not the cause. A "blame the latest deploy" baseline (B4) would pick
        # this one, so commit attribution must look past recency.
        decoy_on = onset + timedelta(seconds=15)
        self.deployments.append(
            {
                "deployment_id": "dep-decoy0001",
                "service_name": "user-service",
                "timestamp": _iso(decoy_on),
                "commit_sha": DECOY_DEPLOY_COMMIT,
                "status": "deployed",
                "changed_files": "services/user_service/app.py",
                "change_summary": "Bump user-service request logging (unrelated to the incident)",
                "ingestion_time": _iso(decoy_on + timedelta(seconds=2)),
            }
        )

    def _emit_alerts(self, incident_start: int, incident_end: int) -> None:
        onset = BASE_TIME + timedelta(milliseconds=500 * incident_start)
        specs = [
            ("PaymentDbPoolSaturation", "payment-service", "critical", "Database connection pool is at the limit", POOL_SIZE),
            ("PaymentHighLatency", "payment-service", "warning", "p95 payment latency above threshold", 2000),
            ("Payment5xxRate", "payment-service", "critical", "payment-service 5xx rate above threshold", 1.0),
            ("OrderHighLatency", "order-service", "warning", "order-service p95 latency above threshold", 2050),
            ("Order5xxRate", "order-service", "critical", "order-service 5xx rate above threshold", 0.5),
            ("Gateway5xxRate", "api-gateway", "critical", "api-gateway 5xx rate above threshold", 0.6),
            ("OrderCpuHigh", "order-service", "warning", "order-service CPU above threshold", 0.85),
            ("PodRestarts", "payment-service", "warning", "payment-service pod restarted", 1),
        ]
        for offset, (name, service, severity, summary, value) in enumerate(specs):
            self.alerts.append(
                {
                    "alertname": name,
                    "service_name": service,
                    "severity": severity,
                    "summary": summary,
                    "value": value,
                    "startsAt": _iso(onset + timedelta(milliseconds=offset * 200)),
                    "labels": {"job": service, "severity": severity},
                    "ingestion_time": _iso(onset + timedelta(milliseconds=offset * 200 + 50)),
                }
            )

    def _plant_corruption(self) -> None:
        d = self.degrade
        if d.invalid_timestamp_count:
            for n in range(d.invalid_timestamp_count):
                self.logs.append(
                    {
                        "timestamp": "not-a-timestamp",
                        "service_name": "payment-service",
                        "severity": "ERROR",
                        "message": "log with corrupt timestamp",
                        "event_type": "LOG",
                    }
                )
                self._record_challenge("invalid_timestamp", f"planted-{n}", "unparseable timestamp")

        if d.out_of_range_count:
            for n in range(d.out_of_range_count):
                self.spans.append(
                    {
                        "trace_id": f"trace-bad{n}",
                        "span_id": f"badspan-{n}",
                        "parent_span_id": None,
                        "service_name": "payment-service",
                        "name": "POST /pay",
                        "kind": "SERVER",
                        "start_time": _iso(BASE_TIME),
                        "end_time": _iso(BASE_TIME),
                        "duration_ms": 9000000,
                        "status_code": 999,
                        "ingestion_time": _iso(BASE_TIME),
                    }
                )
                self._record_challenge("out_of_range", f"badspan-{n}", "impossible duration/status")

        if d.unknown_service_count:
            for n in range(d.unknown_service_count):
                self.logs.append(
                    {
                        "timestamp": _iso(BASE_TIME + timedelta(seconds=n)),
                        "service_name": "payment_svc_v2",
                        "severity": "ERROR",
                        "message": "unknown service emitting logs",
                        "event_type": "LOG",
                    }
                )
                self._record_challenge("unknown_service", f"unknown-{n}", "service not in catalog")

        if d.late_event_count:
            late_time = BASE_TIME - timedelta(minutes=10)
            for n in range(d.late_event_count):
                self.logs.append(
                    {
                        "timestamp": _iso(late_time),
                        "service_name": "order-service",
                        "severity": "WARN",
                        "message": "late-arriving batch log",
                        "event_type": "LOG",
                        "ingestion_time": _iso(BASE_TIME + timedelta(seconds=5)),
                    }
                )
                self._record_challenge("late_event", f"late-{n}", "ingested well after event time")

        # Broken trace link: a span whose parent was never emitted.
        for n in range(d.broken_link_count):
            self.spans.append(
                {
                    "trace_id": f"trace-orphan-{n}",
                    "span_id": f"orphan-{n}",
                    "parent_span_id": f"missing-parent-{n}",
                    "service_name": "order-service",
                    "name": "POST /orders",
                    "kind": "SERVER",
                    "start_time": _iso(BASE_TIME + timedelta(seconds=1)),
                    "end_time": _iso(BASE_TIME + timedelta(seconds=1, milliseconds=10)),
                    "duration_ms": 10,
                    "status_code": 200,
                    "ingestion_time": _iso(BASE_TIME + timedelta(seconds=1)),
                }
            )
            self._record_challenge("broken_trace_link", f"orphan-{n}", "parent span missing")

        if d.duplicate_rate:
            for collection, name in ((self.logs, "log"), (self.metrics, "metric")):
                duplicates = [
                    dict(item) for item in list(collection) if self.rng.random() < d.duplicate_rate
                ]
                for dup in duplicates:
                    collection.append(dup)
                if duplicates:
                    self._record_challenge("duplicate", name, f"{len(duplicates)} duplicated records")


def generate_dataset(
    out_dir: Path,
    scenario: str = "incident-001",
    degrade: DegradeConfig | None = None,
    seed: int = 42,
    requests: int = 60,
) -> dict:
    degrade = degrade or DegradeConfig()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    builder = DatasetBuilder(degrade, seed, requests)
    builder.build()

    _write_jsonl(out_dir / "traces.jsonl", builder.spans)
    _write_jsonl(out_dir / "logs.jsonl", builder.logs)
    _write_csv(
        out_dir / "metrics.csv",
        ["timestamp", "service_name", "metric_name", "value", "ingestion_time"],
        builder.metrics,
    )
    _write_csv(
        out_dir / "deployments.csv",
        [
            "deployment_id",
            "service_name",
            "timestamp",
            "commit_sha",
            "status",
            "changed_files",
            "change_summary",
            "ingestion_time",
        ],
        builder.deployments,
    )
    (out_dir / "alerts.json").write_text(
        json.dumps({"alerts": builder.alerts}, indent=2), encoding="utf-8"
    )
    _write_csv(
        out_dir / "telemetry_quality_challenges.csv",
        ["challenge_type", "source_reference", "description"],
        builder.challenges,
    )

    manifest = {
        "scenario": scenario,
        "seed": seed,
        "requests": requests,
        "degrade": asdict(degrade),
        "counts": {
            "spans": len(builder.spans),
            "logs": len(builder.logs),
            "metrics": len(builder.metrics),
            "deployments": len(builder.deployments),
            "alerts": len(builder.alerts),
            "challenges": len(builder.challenges),
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str) + "\n")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic telemetry for TraceMind AI.")
    parser.add_argument("--out-dir", default="data/synthetic/incident-001")
    parser.add_argument("--scenario", default="incident-001")
    parser.add_argument("--degrade", choices=sorted(DEGRADE_PRESETS), default="none")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--requests", type=int, default=60)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = generate_dataset(
        Path(args.out_dir),
        scenario=args.scenario,
        degrade=DEGRADE_PRESETS[args.degrade],
        seed=args.seed,
        requests=args.requests,
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
