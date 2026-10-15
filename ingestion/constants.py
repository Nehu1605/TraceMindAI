"""Shared constants for telemetry normalization.

Service names are canonicalized here so that ``payment_service``,
``paymentService`` and ``payment`` all resolve to ``payment-service``. This
matters because real telemetry is inconsistent, and identity mismatches are
a common cause of failed correlation.
"""

from __future__ import annotations

CANONICAL_SERVICES: tuple[str, ...] = (
    "api-gateway",
    "order-service",
    "payment-service",
    "user-service",
    "postgres",
)

# Raw spelling -> canonical name.
SERVICE_ALIASES: dict[str, str] = {
    "api-gateway": "api-gateway",
    "api_gateway": "api-gateway",
    "apigateway": "api-gateway",
    "gateway": "api-gateway",
    "order-service": "order-service",
    "order_service": "order-service",
    "orderservice": "order-service",
    "order": "order-service",
    "payment-service": "payment-service",
    "payment_service": "payment-service",
    "paymentservice": "payment-service",
    "payment": "payment-service",
    "user-service": "user-service",
    "user_service": "user-service",
    "userservice": "user-service",
    "user": "user-service",
    "postgres": "postgres",
    "postgresql": "postgres",
    "pgsql": "postgres",
    "db": "postgres",
}

# Canonical severity levels, ordered from least to most severe.
SEVERITY_ALIASES: dict[str, str] = {
    "trace": "TRACE",
    "verbose": "TRACE",
    "debug": "DEBUG",
    "info": "INFO",
    "information": "INFO",
    "notice": "INFO",
    "warn": "WARN",
    "warning": "WARN",
    "error": "ERROR",
    "err": "ERROR",
    "severe": "ERROR",
    "fatal": "FATAL",
    "critical": "FATAL",
    "crit": "FATAL",
    "panic": "FATAL",
}

# Canonical event types used across parsing and later correlation.
EVENT_TYPE_DATABASE_ERROR = "DATABASE_ERROR"
EVENT_TYPE_DB_CONNECTION_TIMEOUT = "DB_CONNECTION_TIMEOUT"
EVENT_TYPE_HTTP_5XX = "HTTP_5XX"
EVENT_TYPE_HTTP_REQUEST = "HTTP_REQUEST"
EVENT_TYPE_DEPLOYMENT = "DEPLOYMENT"
EVENT_TYPE_ALERT = "ALERT"
EVENT_TYPE_METRIC_SAMPLE = "METRIC_SAMPLE"
EVENT_TYPE_SPAN = "SPAN"
EVENT_TYPE_LOG = "LOG"

CANONICAL_EVENT_TYPES: frozenset[str] = frozenset(
    {
        EVENT_TYPE_DATABASE_ERROR,
        EVENT_TYPE_DB_CONNECTION_TIMEOUT,
        EVENT_TYPE_HTTP_5XX,
        EVENT_TYPE_HTTP_REQUEST,
        EVENT_TYPE_DEPLOYMENT,
        EVENT_TYPE_ALERT,
        EVENT_TYPE_METRIC_SAMPLE,
        EVENT_TYPE_SPAN,
        EVENT_TYPE_LOG,
    }
)


def canonical_service(raw: str | None) -> str | None:
    """Return the canonical service name, or ``None`` if unknown/empty."""

    if raw is None:
        return None
    key = raw.strip().lower()
    if not key:
        return None
    return SERVICE_ALIASES.get(key, raw.strip())


def is_known_service(name: str | None) -> bool:
    return name in CANONICAL_SERVICES
