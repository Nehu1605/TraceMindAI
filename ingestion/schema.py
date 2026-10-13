"""The unified event schema.

Every telemetry record - a span, a log line, a metric sample, a deployment
or a raw alert - is normalized into a single ``NormalizedEvent`` shape.
Keeping one schema lets the correlation and RCA phases treat all evidence
uniformly, and matches the data model described in the project README.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    TRACE = "trace"
    LOG = "log"
    METRIC = "metric"
    DEPLOYMENT = "deployment"
    ALERT = "alert"


class Severity(str, Enum):
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"
    UNKNOWN = "UNKNOWN"


class EvidenceQuality(str, Enum):
    """How strongly an event is linked to a request/trace.

    * ``direct``    - the event carries a valid trace/span id.
    * ``inferred``  - linked by service + time window + error signature.
    * ``time_only`` - only a time window links it; weakest.
    * ``unknown``   - not enough information to link at all.
    """

    DIRECT = "direct"
    INFERRED = "inferred"
    TIME_ONLY = "time_only"
    UNKNOWN = "unknown"


def make_event_id(source_type: SourceType, *parts: Any) -> str:
    """Build a deterministic event id from identifying fields.

    Deterministic ids make de-duplication trivial and keep pipeline runs
    reproducible.
    """

    payload = "|".join("" if part is None else str(part) for part in parts)
    digest = hashlib.sha1(f"{source_type.value}|{payload}".encode("utf-8")).hexdigest()
    return f"evt-{digest[:16]}"


class NormalizedEvent(BaseModel):
    event_id: str
    event_time: datetime
    ingestion_time: datetime
    source_type: SourceType
    event_type: str
    service_name: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    severity: Severity = Severity.UNKNOWN
    message: str | None = None
    duration_ms: float | None = None
    status_code: int | None = None
    metric_name: str | None = None
    metric_value: float | None = None
    deployment_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_reference: str = ""
    evidence_quality: EvidenceQuality = EvidenceQuality.UNKNOWN
    is_late: bool = False
    clock_skew_suspected: bool = False

    def to_json(self) -> str:
        return self.model_dump_json()

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_json(cls, raw: str) -> "NormalizedEvent":
        return cls.model_validate(json.loads(raw))
