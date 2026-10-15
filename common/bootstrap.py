"""Shared FastAPI application factory for the demo services.

Centralizing bootstrap keeps every service consistent: JSON logging,
Prometheus metrics, OpenTelemetry tracing, and health endpoints are wired
the same way so that later phases can rely on a uniform telemetry shape.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, Response

from . import metrics
from .config import get_settings
from .logging_config import configure_logging
from .telemetry import setup_telemetry

logger = logging.getLogger(__name__)


def create_app(
    service_name: str,
    title: str,
    description: str = "",
) -> FastAPI:
    """Create and configure a demo FastAPI service."""

    settings = get_settings()
    configure_logging(service_name, settings.environment, settings.log_level)

    app = FastAPI(title=title, description=description, version="0.1.0")
    app.state.service_name = service_name

    if settings.prometheus_enabled:
        metrics.install_http_metrics(app, service_name)

        @app.get("/metrics", include_in_schema=False)
        async def _metrics() -> Response:  # pragma: no cover - trivial
            payload, content_type = metrics.render_metrics()
            return Response(content=payload, media_type=content_type)

    setup_telemetry(
        app,
        service_name=service_name,
        endpoint=settings.otel_exporter_otlp_endpoint,
        enabled=settings.otel_enabled,
    )

    @app.get("/healthz", include_in_schema=False)
    async def _healthz(request: Request) -> dict:  # pragma: no cover - trivial
        from . import db

        db_ok = db.check_health(request.app.state.service_name)
        return {"status": "ok" if db_ok else "degraded", "service": service_name, "database_ok": db_ok}

    logger.info("Service %s initialized", service_name)
    return app
