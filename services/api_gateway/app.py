"""API Gateway.

The single entry point used by the load generator. It forwards order
requests to the order-service. When the downstream call fails, the gateway
returns HTTP 500 - the exact symptom observed by users during the incident.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException

from common.bootstrap import create_app
from common.config import get_settings
from common.errors import DownstreamServiceError
from common.http_client import new_client, request_json
from common.metrics import APP_ERRORS_TOTAL
from common.models import HealthResponse, OrderRequest, OrderResponse

SERVICE_NAME = "api-gateway"

app = create_app(
    SERVICE_NAME,
    title="TraceMind API Gateway",
    description="Public entry point that fronts the order-service.",
)

logger = logging.getLogger(__name__)
settings = get_settings()


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:  # pragma: no cover - trivial
    return HealthResponse(status="ok", service=SERVICE_NAME, database_ok=True)


@app.post("/alerts")
async def receive_alerts(payload: dict) -> dict:
    """Receive Alertmanager webhook batches (improvement I10).

    Raw alerts land here in Docker Compose runs; the Phase 2 ingestion
    pipeline consumes them and later phases measure alert reduction.
    """

    alerts = payload.get("alerts", []) if isinstance(payload, dict) else []
    logger.warning(
        "Received alert batch",
        extra={"event_type": "ALERT_BATCH", "count": len(alerts)},
    )
    return {"status": "received", "count": len(alerts)}


@app.post("/orders", response_model=OrderResponse)
async def create_order(request: OrderRequest) -> OrderResponse:
    async with new_client() as client:
        try:
            result = await request_json(
                client,
                "POST",
                f"{settings.order_service_url}/orders",
                service="order-service",
                json=request.model_dump(),
            )
        except DownstreamServiceError as exc:
            APP_ERRORS_TOTAL.labels(SERVICE_NAME, "ORDER_SERVICE_ERROR").inc()
            logger.error(
                "Order request failed",
                extra={"event_type": "GATEWAY_ERROR", "detail": str(exc)},
            )
            raise HTTPException(status_code=500, detail="order-service unavailable")

    logger.info("Request served", extra={"event_type": "REQUEST_SERVED"})
    return OrderResponse(**result)
