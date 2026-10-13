"""Normalization helpers: timestamps, service names, severities and ids.

Normalization is deliberately forgiving: instead of throwing away a record
because one field is odd, we clean what we can and let the validator decide
whether the record is usable. This mirrors the improvement plan's point that
real telemetry is messy (I6).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from .constants import SEVERITY_ALIASES, canonical_service
from .schema import EvidenceQuality, Severity

_Z_SUFFIX = "Z"


def parse_timestamp(value: Any) -> datetime | None:
    """Parse a timestamp into an aware UTC ``datetime`` or return ``None``.

    Accepts ISO 8601 strings (with or without ``Z``/offset) and epoch
    seconds or milliseconds.
    """

    if value is None:
        return None

    if isinstance(value, bool):  # bool is a subclass of int; never a timestamp
        return None

    if isinstance(value, (int, float)):
        return _from_epoch(float(value))

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # Numeric strings are treated as epoch values.
        try:
            return _from_epoch(float(text))
        except ValueError:
            pass
        if text.endswith(_Z_SUFFIX):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    return None


def _from_epoch(value: float) -> datetime | None:
    if not math.isfinite(value):
        return None
    # Anything larger than this is almost certainly milliseconds.
    if abs(value) > 1e12:
        value = value / 1000.0
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def normalize_service(value: Any) -> str | None:
    if value is None:
        return None
    return canonical_service(str(value))


def normalize_severity(value: Any) -> Severity:
    if value is None:
        return Severity.UNKNOWN
    key = str(value).strip().lower()
    canonical = SEVERITY_ALIASES.get(key)
    if canonical is None:
        return Severity.UNKNOWN
    return Severity(canonical)


def normalize_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def normalize_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def evidence_quality_for(
    trace_id: str | None, span_id: str | None, service_name: str | None
) -> EvidenceQuality:
    """Assign an initial evidence-quality label at ingestion time.

    A direct trace/span link is the strongest. When the trace id is missing
    but the service is known, the event can still be correlated later by
    service and time window, so it is labelled ``time_only``. Full
    ``inferred`` labels are produced during correlation (Phase 3) when an
    error signature match is available.
    """

    if trace_id and span_id:
        return EvidenceQuality.DIRECT
    if trace_id:
        return EvidenceQuality.DIRECT
    if service_name:
        return EvidenceQuality.TIME_ONLY
    return EvidenceQuality.UNKNOWN
