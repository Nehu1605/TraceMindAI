"""Unit tests for the raw-telemetry parsers (Phase 2)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ingestion.parsers import (
    parse_alerts,
    parse_deployments,
    parse_logs,
    parse_metrics,
    parse_raw_directory,
    parse_traces,
)
from ingestion.schema import SourceType

NOW = datetime(2026, 10, 11, 10, 0, 0, tzinfo=timezone.utc)


def write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_parse_traces_span(tmp_path):
    path = tmp_path / "traces.jsonl"
    write_jsonl(
        path,
        [
            {
                "trace_id": "t1",
                "span_id": "s1",
                "service_name": "payment_service",
                "name": "POST /pay",
                "start_time": "2026-10-11T10:00:00Z",
                "duration_ms": 12,
                "status_code": 200,
            }
        ],
    )

    records = parse_traces(path, NOW)

    assert len(records) == 1
    event = records[0].event
    assert event is not None
    assert event.source_type == SourceType.TRACE
    assert event.service_name == "payment-service"
    assert event.duration_ms == 12


def test_parse_traces_malformed_line_is_quarantinable(tmp_path):
    path = tmp_path / "traces.jsonl"
    path.write_text("{not json}\n", encoding="utf-8")

    records = parse_traces(path, NOW)

    assert records[0].event is None
    assert records[0].reasons


def test_parse_traces_invalid_timestamp(tmp_path):
    path = tmp_path / "traces.jsonl"
    write_jsonl(
        path,
        [{"trace_id": "t1", "span_id": "s1", "service_name": "payment-service", "start_time": "bad"}],
    )

    records = parse_traces(path, NOW)

    assert records[0].event is None
    assert "invalid_timestamp" in records[0].reasons


def test_parse_logs_canonicalizes_severity(tmp_path):
    path = tmp_path / "logs.jsonl"
    write_jsonl(
        path,
        [
            {
                "timestamp": "2026-10-11T10:00:00Z",
                "service_name": "order",
                "severity": "warning",
                "message": "slow",
                "trace_id": "t1",
                "span_id": "s1",
            }
        ],
    )

    records = parse_logs(path, NOW)

    assert records[0].event.severity.value == "WARN"
    assert records[0].event.service_name == "order-service"


def test_parse_metrics_and_deployments(tmp_path):
    metrics = tmp_path / "metrics.csv"
    metrics.write_text(
        "timestamp,service_name,metric_name,value\n"
        "2026-10-11T10:00:00Z,payment-service,http_5xx_rate,0.5\n",
        encoding="utf-8",
    )
    deployments = tmp_path / "deployments.csv"
    deployments.write_text(
        "deployment_id,service_name,timestamp,commit_sha,status,changed_files,change_summary\n"
        "dep-1,payment-service,2026-10-11T09:59:00Z,abc,deployed,a.py,defect\n",
        encoding="utf-8",
    )

    metric_events = parse_metrics(metrics)
    deploy_events = parse_deployments(deployments)

    assert metric_events[0].event.metric_value == 0.5
    assert deploy_events[0].event.deployment_id == "dep-1"


def test_parse_alerts(tmp_path):
    path = tmp_path / "alerts.json"
    path.write_text(
        json.dumps(
            {
                "alerts": [
                    {
                        "alertname": "Payment5xxRate",
                        "service_name": "payment-service",
                        "severity": "critical",
                        "summary": "high 5xx",
                        "startsAt": "2026-10-11T10:00:00Z",
                        "labels": {"job": "payment-service"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    records = parse_alerts(path, NOW)

    assert len(records) == 1
    assert records[0].event.source_type == SourceType.ALERT
    assert records[0].event.severity.value == "FATAL"


def test_parse_raw_directory_reads_all_known_files(tmp_path):
    write_jsonl(
        tmp_path / "traces.jsonl",
        [{"trace_id": "t", "span_id": "s", "service_name": "payment-service", "start_time": "2026-10-11T10:00:00Z"}],
    )
    write_jsonl(
        tmp_path / "logs.jsonl",
        [{"timestamp": "2026-10-11T10:00:00Z", "service_name": "payment-service", "message": "hi"}],
    )

    records = parse_raw_directory(tmp_path, NOW)

    assert len(records) == 2
