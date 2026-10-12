"""OpenTelemetry wiring shared by every demo service.

Phase 1 only needs *identifiable* telemetry: every service must export
traces (with trace/span ids) so that later phases can correlate events.
If the OpenTelemetry packages are not installed, tracing degrades to a no-op
instead of crashing the service.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def setup_telemetry(app: Any, service_name: str, endpoint: str, enabled: bool = True) -> bool:
    """Configure the OTLP exporter and instrument FastAPI + httpx.

    Returns ``True`` when tracing was configured, ``False`` when it was
    skipped (disabled or dependencies missing).
    """

    if not enabled:
        logger.info("OpenTelemetry disabled; skipping tracing setup")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception as exc:  # pragma: no cover - depends on optional deps
        logger.warning("OpenTelemetry libraries unavailable (%s); tracing disabled", exc)
        return False

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "tracemind",
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    logger.info("OpenTelemetry tracing enabled (endpoint=%s)", endpoint)
    return True
