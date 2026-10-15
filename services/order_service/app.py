"""Order Service.

Orchestrates an order by calling the user-service (validation) and the
payment-service (charging). It contains no injected defect of its own, so
any failures it reports must originate downstream - which is exactly the
propagation path the RCA engine must learn to explain.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import HTTPException

from common.bootstrap import create_app
from common.config import get_settings
from common.errors import DownstreamServiceError
from common.http_client import new_client, request_json
from common.metrics import APP_ERRORS_TOTAL
from common.models import HealthResponse, OrderRequest, OrderResponse

SERVICE_NAME = "order-service"

app = create_app(
    SERVICE_NAME,
    title="TraceMind Order Service",
    description="Orchestrates orders across user-service and payment-service.",
)

logger = logging.getLogger(__name__)
settings = get_settings()


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:  # pragma: no cover - trivial
    return HealthResponse(status="ok", service=SERVICE_NAME, database_ok=True)


@app.post("/orders", response_model=OrderResponse)
async def create_order(request: OrderRequest) -> OrderResponse:
    order_id = f"ord-{uuid.uuid4().hex[:12]}"

    async with new_client() as client:
        try:
            await request_json(
                client,
                "GET",
                f"{settings.user_service_url}/users/{request.user_id}",
                service="user-service",
            )
        except DownstreamServiceError as exc:
            APP_ERRORS_TOTAL.labels(SERVICE_NAME, "USER_SERVICE_ERROR").inc()
            logger.error(
                "User validation failed",
                extra={"event_type": "DOWNSTREAM_ERROR", "order_id": order_id, "detail": str(exc)},
            )
            raise HTTPException(status_code=502, detail="user-service unavailable")

        try:
            payment = await request_json(
                client,
                "POST",
                f"{settings.payment_service_url}/pay",
                service="payment-service",
                json={
                    "order_id": order_id,
                    "user_id": request.user_id,
                    "amount": request.amount,
                    "currency": request.currency,
                },
            )
        except DownstreamServiceError as exc:
            APP_ERRORS_TOTAL.labels(SERVICE_NAME, "PAYMENT_SERVICE_ERROR").inc()
            logger.error(
                "Payment failed",
                extra={"event_type": "DOWNSTREAM_ERROR", "order_id": order_id, "detail": str(exc)},
            )
            raise HTTPException(status_code=502, detail="payment-service unavailable")

    logger.info(
        "Order completed",
        extra={"event_type": "ORDER_COMPLETED", "order_id": order_id},
    )
    return OrderResponse(
        order_id=order_id,
        status="CONFIRMED",
        user_id=request.user_id,
        amount=request.amount,
        currency=request.currency,
        payment_id=(payment or {}).get("payment_id"),
    )
