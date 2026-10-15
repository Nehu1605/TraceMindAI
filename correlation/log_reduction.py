"""Log-volume reduction (improvement I10, log-cost half).

The plan promises lower log-ingestion cost. Two things are needed:

1. Collapse repeated log lines into *templates* with counts (a Drain-style
   template key, implemented with simple placeholder rules here).
2. Keep full logs only for the time windows linked to an incident and sample
   the rest, then report bytes retained against bytes ingested.

Template mining never drops information on its own - it always produces a
summary - so ``mine_templates`` is safe to run over everything. ``reduce_logs``
applies the retention policy and returns both the retained events and the
byte-level measurement.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ingestion.schema import NormalizedEvent, Severity, SourceType

_CRITICAL = {Severity.ERROR, Severity.FATAL}

_TEMPLATE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?"), "<TS>"),
    (
        re.compile(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
        ),
        "<ID>",
    ),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<IP>"),
    (re.compile(r"\b[0-9a-fA-F]{8,}\b"), "<HEX>"),
    (re.compile(r"\b\d+(?:\.\d+)?\b"), "<NUM>"),
]


def template_of(message: str | None) -> str:
    """Reduce a log line to a stable template key.

    Numbers, ids, addresses and timestamps are replaced by placeholders so
    that ``connection pool exhausted (active=9)`` and
    ``connection pool exhausted (active=10)`` share one template.
    """

    if not message:
        return ""
    text = message
    for pattern, replacement in _TEMPLATE_RULES:
        text = pattern.sub(replacement, text)
    return " ".join(text.split())


def _message_bytes(event: NormalizedEvent) -> int:
    return len((event.message or "").encode("utf-8"))


def mine_templates(events: list[NormalizedEvent]) -> list[dict]:
    """Group log events into templates with counts and byte totals."""

    templates: dict[tuple[str, str], dict] = {}
    for event in events:
        if event.source_type != SourceType.LOG:
            continue
        key = (event.service_name or "", template_of(event.message))
        entry = templates.get(key)
        if entry is None:
            templates[key] = {
                "service": event.service_name or "",
                "template": key[1],
                "count": 1,
                "bytes": _message_bytes(event),
                "example": event.message,
                "first_seen": event.event_time.isoformat(),
                "last_seen": event.event_time.isoformat(),
            }
            continue
        entry["count"] += 1
        entry["bytes"] += _message_bytes(event)
        if event.event_time < datetime.fromisoformat(entry["first_seen"]):
            entry["first_seen"] = event.event_time.isoformat()
        if event.event_time > datetime.fromisoformat(entry["last_seen"]):
            entry["last_seen"] = event.event_time.isoformat()

    return sorted(templates.values(), key=lambda t: t["count"], reverse=True)


@dataclass
class LogReductionResult:
    log_count_total: int = 0
    log_count_retained: int = 0
    template_count: int = 0
    unique_lines: int = 0
    bytes_ingested: int = 0
    bytes_retained: int = 0
    kept_events: list[NormalizedEvent] = field(default_factory=list)
    templates: list[dict] = field(default_factory=list)

    @property
    def template_reduction_pct(self) -> float:
        """Distinct raw lines collapsed away by template mining."""

        if self.unique_lines == 0:
            return 0.0
        return round((1.0 - self.template_count / self.unique_lines) * 100.0, 2)

    @property
    def bytes_reduction_pct(self) -> float:
        if self.bytes_ingested == 0:
            return 0.0
        retained = 1.0 - (self.bytes_retained / self.bytes_ingested)
        return round(retained * 100.0, 2)

    @property
    def log_reduction_pct(self) -> float:
        if self.log_count_total == 0:
            return 0.0
        retained = 1.0 - (self.log_count_retained / self.log_count_total)
        return round(retained * 100.0, 2)

    def to_dict(self) -> dict:
        return {
            "log_count_total": self.log_count_total,
            "log_count_retained": self.log_count_retained,
            "log_reduction_pct": self.log_reduction_pct,
            "template_count": self.template_count,
            "unique_lines": self.unique_lines,
            "template_reduction_pct": self.template_reduction_pct,
            "bytes_ingested": self.bytes_ingested,
            "bytes_retained": self.bytes_retained,
            "bytes_reduction_pct": self.bytes_reduction_pct,
            "templates": self.templates,
        }


def windows_from_incidents(
    incidents: list[dict],
    pad_seconds: float = 60.0,
) -> list[tuple[datetime, datetime]]:
    """Turn incident start/end times into padded retention windows."""

    pad = timedelta(seconds=pad_seconds)
    windows: list[tuple[datetime, datetime]] = []
    for incident in incidents:
        start = datetime.fromisoformat(incident["start_time"])
        end = datetime.fromisoformat(incident["end_time"])
        windows.append((start - pad, end + pad))
    return windows


def _in_windows(when: datetime, windows: list[tuple[datetime, datetime]]) -> bool:
    return any(start <= when <= end for start, end in windows)


def _sampled(event_id: str, rate: float) -> bool:
    """Deterministic sampling so pipeline runs stay reproducible."""

    if rate <= 0.0:
        return False
    if rate >= 1.0:
        return True
    digest = hashlib.sha1(event_id.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 10_000
    return bucket < int(rate * 10_000)


def reduce_logs(
    events: list[NormalizedEvent],
    keep_windows: list[tuple[datetime, datetime]] | None = None,
    sample_rate: float = 0.0,
) -> LogReductionResult:
    """Apply the log-retention policy and measure the byte reduction.

    Logs inside an incident window (or of ERROR/FATAL severity, which are
    cheap and valuable) are always kept; the remaining logs are sampled at
    ``sample_rate`` (default 0.0, i.e. dropped). Non-log events are always
    kept. When ``keep_windows`` is ``None`` every error-tier log is still
    retained, so a bare call degrades to "keep errors" rather than dropping
    everything.
    """

    windows = keep_windows or []
    result = LogReductionResult()
    result.templates = mine_templates(events)

    unique_messages: set[str] = set()
    for event in events:
        if event.source_type != SourceType.LOG:
            result.kept_events.append(event)
            continue
        result.log_count_total += 1
        result.bytes_ingested += _message_bytes(event)
        unique_messages.add(event.message or "")

        keep = (
            _in_windows(event.event_time, windows)
            or event.severity in _CRITICAL
            or _sampled(event.event_id, sample_rate)
        )
        if keep:
            result.kept_events.append(event)
            result.log_count_retained += 1
            result.bytes_retained += _message_bytes(event)

    result.template_count = len(result.templates)
    result.unique_lines = len(unique_messages)
    return result
