"""Unit tests for normalization helpers (Phase 2, improvement I6)."""

from __future__ import annotations

from datetime import timezone

import pytest

from ingestion.constants import canonical_service
from ingestion.normalize import (
    evidence_quality_for,
    normalize_float,
    normalize_id,
    normalize_int,
    normalize_severity,
    normalize_service,
    parse_timestamp,
)
from ingestion.schema import EvidenceQuality, Severity


def test_parse_timestamp_accepts_iso_z():
    parsed = parse_timestamp("2026-10-11T10:00:00Z")
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed.astimezone(timezone.utc).hour == 10


def test_parse_timestamp_accepts_naive_and_assumes_utc():
    parsed = parse_timestamp("2026-10-11T10:00:00")
    assert parsed is not None
    assert parsed.tzinfo == timezone.utc


def test_parse_timestamp_accepts_epoch_seconds_and_ms():
    seconds = parse_timestamp(1_700_000_000)
    millis = parse_timestamp(1_700_000_000_000)
    assert seconds == millis


@pytest.mark.parametrize("bad", ["", "   ", "not-a-timestamp", None, True, float("inf")])
def test_parse_timestamp_rejects_garbage(bad):
    assert parse_timestamp(bad) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("payment_service", "payment-service"),
        ("paymentService", "payment-service"),
        ("gateway", "api-gateway"),
        ("postgresql", "postgres"),
        ("  ORDER-SERVICE ", "order-service"),
    ],
)
def test_normalize_service_aliases(raw, expected):
    assert normalize_service(raw) == expected


def test_normalize_service_returns_raw_when_unknown():
    assert canonical_service("payment_svc_v2") == "payment_svc_v2"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("warning", Severity.WARN),
        ("CRITICAL", Severity.FATAL),
        ("err", Severity.ERROR),
        ("nonsense", Severity.UNKNOWN),
        (None, Severity.UNKNOWN),
    ],
)
def test_normalize_severity(raw, expected):
    assert normalize_severity(raw) == expected


def test_normalize_scalars():
    assert normalize_float("3.5") == 3.5
    assert normalize_float("") is None
    assert normalize_float("nan") is None
    assert normalize_int("42") == 42
    assert normalize_int("x") is None
    assert normalize_id("  abc ") == "abc"
    assert normalize_id("   ") is None


def test_evidence_quality_labels():
    assert evidence_quality_for("t", "s", "svc") == EvidenceQuality.DIRECT
    assert evidence_quality_for(None, None, "svc") == EvidenceQuality.TIME_ONLY
    assert evidence_quality_for(None, None, None) == EvidenceQuality.UNKNOWN
