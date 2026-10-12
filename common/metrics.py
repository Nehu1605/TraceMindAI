"""Prometheus metrics and the HTTP instrumentation middleware.

Phase 1 emits the baseline signals the RCA engine will consume later:
request rate, request latency, HTTP 5xx counts, and database connection
utilization (the key signal for the primary incident).
"""

from __future__ import annotations

import time
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

REGISTRY = CollectorRegistry(auto_describe=True)

HTTP_REQUESTS_TOTAL = Counter(
    "tracemind_http_requests_total",
    "Total HTTP requests handled, labelled by service/method/path/status.",
    ["service", "method", "path", "status"],
    registry=REGISTRY,
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "tracemind_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["service", "method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)

DB_CONNECTIONS_IN_USE = Gauge(
    "tracemind_db_connections_in_use",
    "Number of currently checked-out database connections.",
    ["service"],
    registry=REGISTRY,
)

DB_POOL_SIZE_GAUGE = Gauge(
    "tracemind_db_pool_size",
    "Configured maximum size of the database connection pool.",
    ["service"],
    registry=REGISTRY,
)

DB_CONNECTION_ERRORS_TOTAL = Counter(
    "tracemind_db_connection_errors_total",
    "Database connection acquisition failures (pool exhaustion / timeouts).",
    ["service"],
    registry=REGISTRY,
)

APP_ERRORS_TOTAL = Counter(
    "tracemind_app_errors_total",
    "Application-level errors labelled by error type.",
    ["service", "error_type"],
    registry=REGISTRY,
)


def install_http_metrics(app: Any, service_name: str) -> None:
    """Attach a middleware that records request count and latency."""

    @app.middleware("http")
    async def _metrics_middleware(request, call_next):  # type: ignore[no-untyped-def]
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        method = request.method
        status = str(response.status_code)

        HTTP_REQUESTS_TOTAL.labels(service_name, method, path, status).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(service_name, method, path).observe(elapsed)
        return response


def render_metrics() -> tuple[bytes, str]:
    """Return the latest Prometheus exposition payload and content type."""

    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
