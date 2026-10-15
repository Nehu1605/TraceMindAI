"""Structured JSON logging with trace/span context for correlation.

Logs are emitted as single-line JSON so the Phase 2 ingestion pipeline can
parse them deterministically. When a request is inside an active span, the
``trace_id`` and ``span_id`` fields are attached automatically, which is what
allows Phase 3 to correlate logs with distributed traces.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

try:  # OpenTelemetry is optional at import time.
    from opentelemetry import trace
except Exception:  # pragma: no cover - exercised only without OTel installed
    trace = None  # type: ignore[assignment]

_RESERVED = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",
    "message",
    "asctime",
}


def _current_trace_context() -> tuple[str | None, str | None]:
    if trace is None:
        return None, None
    try:
        ctx = trace.get_current_span().get_span_context()
    except Exception:  # pragma: no cover - defensive
        return None, None
    if not ctx or not ctx.is_valid:
        return None, None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")


class JsonFormatter(logging.Formatter):
    """Render log records as compact JSON objects."""

    def __init__(self, service_name: str, environment: str) -> None:
        super().__init__()
        self.service_name = service_name
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        trace_id, span_id = _current_trace_context()
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat().replace("+00:00", "Z"),
            "severity": record.levelname,
            "service": self.service_name,
            "environment": self.environment,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": trace_id,
            "span_id": span_id,
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(
    service_name: str, environment: str = "local", level: str = "INFO"
) -> None:
    """Install the JSON formatter on the root logger exactly once."""

    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter(service_name, environment))
    root.addHandler(handler)
