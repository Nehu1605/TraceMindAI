"""User Service.

A simple, healthy downstream dependency: it validates a user id and reads
the user profile from PostgreSQL. It is intentionally fault-free so that it
serves as a control when analysing the primary incident.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request

from common import db
from common.bootstrap import create_app
from common.config import get_settings
from common.errors import DatabaseError
from common.metrics import APP_ERRORS_TOTAL
from common.models import HealthResponse, UserResponse

SERVICE_NAME = "user-service"

app = create_app(
    SERVICE_NAME,
    title="TraceMind User Service",
    description="Resolves user profiles from PostgreSQL.",
)

logger = logging.getLogger(__name__)
settings = get_settings()

_TIERS = {"user-1": "gold", "user-2": "silver", "user-3": "bronze"}


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:  # pragma: no cover - trivial
    db_ok = db.check_health(SERVICE_NAME)
    return HealthResponse(status="ok" if db_ok else "degraded", service=SERVICE_NAME, database_ok=db_ok)


@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, request: Request) -> UserResponse:
    try:
        with db.connection(SERVICE_NAME) as conn:
            rows = conn.execute("SELECT 1")
    except DatabaseError as exc:
        APP_ERRORS_TOTAL.labels(SERVICE_NAME, "DATABASE_ERROR").inc()
        logger.error(
            "User lookup failed",
            extra={"event_type": "DATABASE_ERROR", "user_id": user_id, "detail": str(exc)},
        )
        raise HTTPException(status_code=503, detail="database unavailable")

    if not rows:  # pragma: no cover - defensive
        raise HTTPException(status_code=404, detail="user not found")

    logger.info("User resolved", extra={"event_type": "USER_RESOLVED", "user_id": user_id})
    return UserResponse(user_id=user_id, name=f"Demo {user_id}", tier=_TIERS.get(user_id, "standard"))
