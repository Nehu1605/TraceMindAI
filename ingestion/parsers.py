"""Parsers that turn raw telemetry files into normalized events.

Supported raw sources:

* ``traces.jsonl``      - one span per line (OpenTelemetry-style fields)
* ``logs.jsonl``        - one structured log per line
* ``metrics.csv``       - metric samples
* ``deployments.csv``   - deployment/change records
* ``alerts.json``       - raw alert notifications (improvement I10)

Each parser is tolerant of malformed input: bad records are returned as
``ParsedRecord`` objects with an ``event`` of ``None`` and a reason, so the
pipeline can quarantine them instead of crashing.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import (
    EVENT_TYPE_ALERT,
    EVENT_TYPE_DEPLOYMENT,
    EVENT_TYPE_LOG,
    EVENT_TYPE_METRIC_SAMPLE,
    EVENT_TYPE_SPAN,
)
from .normalize import (
    evidence_quality_for,
    normalize_float,
    normalize_id,
    normalize_int,
    normalize_severity,
    normalize_service,
    parse_timestamp,
)
from .schema import EvidenceQuality, NormalizedEvent, Severity, SourceType, make_event_id
from .validation import REASON_INVALID_TIMESTAMP, REASON_MALFORMED_JSON


@dataclass
class ParsedRecord:
    event: NormalizedEvent | None
    raw: dict[str, Any]
    reasons: list[str] = field(default_factory=list)
    source_reference: str = ""


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _read_jsonl(path: Path) -> list[ParsedRecord]:
    records: list[ParsedRecord] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        reference = f"{path.name}:{index}"
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            records.append(
                ParsedRecord(None, {"line": line}, [REASON_MALFORMED_JSON], reference)
            )
            continue
        if not isinstance(obj, dict):
            records.append(
                ParsedRecord(None, {"value": obj}, [REASON_MALFORMED_JSON], reference)
            )
            continue
        records.append(ParsedRecord(None, obj, [], reference))
    return records


def _span_event(obj: dict[str, Any], reference: str, now: datetime) -> ParsedRecord:
    start = parse_timestamp(obj.get("start_time") or obj.get("timestamp"))
    ingestion = parse_timestamp(obj.get("ingestion_time")) or now
    if start is None:
        return ParsedRecord(None, obj, [REASON_INVALID_TIMESTAMP], reference)

    trace_id = normalize_id(obj.get("trace_id"))
    span_id = normalize_id(obj.get("span_id"))
    parent = normalize_id(obj.get("parent_span_id"))
    service = normalize_service(obj.get("service_name") or obj.get("service"))
    status = normalize_int(obj.get("status_code"))
    duration = normalize_float(obj.get("duration_ms"))
    if duration is None and obj.get("end_time"):
        end = parse_timestamp(obj.get("end_time"))
        if end is not None:
            duration = (end - start).total_seconds() * 1000.0

    severity = Severity.ERROR if (status is not None and status >= 500) else Severity.INFO
    event = NormalizedEvent(
        event_id=make_event_id(SourceType.TRACE, trace_id, span_id, service, obj.get("name")),
        event_time=start,
        ingestion_time=ingestion,
        source_type=SourceType.TRACE,
        event_type=EVENT_TYPE_SPAN,
        service_name=service,
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent,
        severity=severity,
        message=obj.get("name"),
        duration_ms=duration,
        status_code=status,
        attributes={
            "kind": obj.get("kind"),
            "status_message": obj.get("status_message"),
        },
        source_reference=reference,
        evidence_quality=evidence_quality_for(trace_id, span_id, service),
    )
    return ParsedRecord(event, obj, [], reference)


def _log_event(obj: dict[str, Any], reference: str, now: datetime) -> ParsedRecord:
    when = parse_timestamp(obj.get("timestamp") or obj.get("time"))
    ingestion = parse_timestamp(obj.get("ingestion_time")) or now
    if when is None:
        return ParsedRecord(None, obj, [REASON_INVALID_TIMESTAMP], reference)

    trace_id = normalize_id(obj.get("trace_id"))
    span_id = normalize_id(obj.get("span_id"))
    service = normalize_service(obj.get("service_name") or obj.get("service"))
    severity = normalize_severity(obj.get("severity") or obj.get("level"))
    message = obj.get("message")

    event = NormalizedEvent(
        event_id=make_event_id(SourceType.LOG, when.isoformat(), service, message),
        event_time=when,
        ingestion_time=ingestion,
        source_type=SourceType.LOG,
        event_type=obj.get("event_type") or EVENT_TYPE_LOG,
        service_name=service,
        trace_id=trace_id,
        span_id=span_id,
        severity=severity,
        message=message,
        status_code=normalize_int(obj.get("status_code")),
        attributes={"logger": obj.get("logger")},
        source_reference=reference,
        evidence_quality=evidence_quality_for(trace_id, span_id, service),
    )
    return ParsedRecord(event, obj, [], reference)


def _metric_event(obj: dict[str, Any], reference: str) -> ParsedRecord:
    when = parse_timestamp(obj.get("timestamp") or obj.get("time"))
    ingestion = parse_timestamp(obj.get("ingestion_time")) or _now()
    if when is None:
        return ParsedRecord(None, obj, [REASON_INVALID_TIMESTAMP], reference)

    service = normalize_service(obj.get("service_name") or obj.get("service"))
    metric_name = normalize_id(obj.get("metric_name") or obj.get("name"))
    value = normalize_float(obj.get("value") if "value" in obj else obj.get("metric_value"))

    event = NormalizedEvent(
        event_id=make_event_id(SourceType.METRIC, when.isoformat(), service, metric_name),
        event_time=when,
        ingestion_time=ingestion,
        source_type=SourceType.METRIC,
        event_type=EVENT_TYPE_METRIC_SAMPLE,
        service_name=service,
        metric_name=metric_name,
        metric_value=value,
        severity=Severity.INFO,
        message=metric_name,
        attributes={"labels": obj.get("labels", {})},
        source_reference=reference,
        evidence_quality=EvidenceQuality.TIME_ONLY if service else EvidenceQuality.UNKNOWN,
    )
    return ParsedRecord(event, obj, [], reference)


def _deployment_event(obj: dict[str, Any], reference: str) -> ParsedRecord:
    when = parse_timestamp(obj.get("timestamp") or obj.get("time"))
    ingestion = parse_timestamp(obj.get("ingestion_time")) or _now()
    if when is None:
        return ParsedRecord(None, obj, [REASON_INVALID_TIMESTAMP], reference)

    service = normalize_service(obj.get("service_name") or obj.get("service"))
    event = NormalizedEvent(
        event_id=make_event_id(
            SourceType.DEPLOYMENT, obj.get("deployment_id"), service, obj.get("commit_sha")
        ),
        event_time=when,
        ingestion_time=ingestion,
        source_type=SourceType.DEPLOYMENT,
        event_type=EVENT_TYPE_DEPLOYMENT,
        service_name=service,
        severity=Severity.INFO,
        message=obj.get("change_summary") or obj.get("message"),
        deployment_id=normalize_id(obj.get("deployment_id")),
        attributes={
            "commit_sha": obj.get("commit_sha"),
            "changed_files": obj.get("changed_files"),
            "status": obj.get("status"),
        },
        source_reference=reference,
        evidence_quality=EvidenceQuality.TIME_ONLY if service else EvidenceQuality.UNKNOWN,
    )
    return ParsedRecord(event, obj, [], reference)


def _alert_event(obj: dict[str, Any], reference: str, now: datetime) -> ParsedRecord:
    when = parse_timestamp(obj.get("startsAt") or obj.get("timestamp"))
    ingestion = parse_timestamp(obj.get("ingestion_time")) or now
    if when is None:
        return ParsedRecord(None, obj, [REASON_INVALID_TIMESTAMP], reference)

    service = normalize_service(obj.get("service_name") or obj.get("service"))
    severity = normalize_severity(obj.get("severity"))
    alertname = normalize_id(obj.get("alertname") or obj.get("name"))
    event = NormalizedEvent(
        event_id=make_event_id(SourceType.ALERT, alertname, service, when.isoformat()),
        event_time=when,
        ingestion_time=ingestion,
        source_type=SourceType.ALERT,
        event_type=EVENT_TYPE_ALERT,
        service_name=service,
        severity=severity,
        message=obj.get("summary") or obj.get("message") or alertname,
        attributes={
            "alertname": alertname,
            "value": obj.get("value"),
            "labels": obj.get("labels", {}),
        },
        source_reference=reference,
        evidence_quality=EvidenceQuality.TIME_ONLY if service else EvidenceQuality.UNKNOWN,
    )
    return ParsedRecord(event, obj, [], reference)


def parse_traces(path: Path, now: datetime | None = None) -> list[ParsedRecord]:
    now = now or _now()
    records: list[ParsedRecord] = []
    for record in _read_jsonl(path):
        if record.reasons:
            records.append(record)
        else:
            records.append(_span_event(record.raw, record.source_reference, now))
    return records


def parse_logs(path: Path, now: datetime | None = None) -> list[ParsedRecord]:
    now = now or _now()
    records: list[ParsedRecord] = []
    for record in _read_jsonl(path):
        if record.reasons:
            records.append(record)
        else:
            records.append(_log_event(record.raw, record.source_reference, now))
    return records


def _read_csv(path: Path) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader, start=2):
            rows.append((f"{path.name}:{index}", row))
    return rows


def parse_metrics(path: Path) -> list[ParsedRecord]:
    return [_metric_event(row, ref) for ref, row in _read_csv(path)]


def parse_deployments(path: Path) -> list[ParsedRecord]:
    return [_deployment_event(row, ref) for ref, row in _read_csv(path)]


def parse_alerts(path: Path, now: datetime | None = None) -> list[ParsedRecord]:
    now = now or _now()
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]]
    if isinstance(payload, dict):
        entries = payload.get("alerts", [])
    elif isinstance(payload, list):
        entries = payload
    else:
        entries = []
    records: list[ParsedRecord] = []
    for index, obj in enumerate(entries, start=1):
        reference = f"{path.name}:{index}"
        if not isinstance(obj, dict):
            records.append(
                ParsedRecord(None, {"value": obj}, [REASON_MALFORMED_JSON], reference)
            )
            continue
        records.append(_alert_event(obj, reference, now))
    return records


_KNOWN_FILES = {
    "traces.jsonl": parse_traces,
    "logs.jsonl": parse_logs,
    "metrics.csv": parse_metrics,
    "deployments.csv": parse_deployments,
    "alerts.json": parse_alerts,
}


def parse_raw_directory(raw_dir: Path, now: datetime | None = None) -> list[ParsedRecord]:
    """Parse every recognized raw telemetry file in ``raw_dir``."""

    records: list[ParsedRecord] = []
    for name, parser in _KNOWN_FILES.items():
        candidate = raw_dir / name
        if candidate.exists():
            if parser in (parse_metrics, parse_deployments):
                records.extend(parser(candidate))  # type: ignore[misc]
            else:
                records.extend(parser(candidate, now))  # type: ignore[misc]
    return records
