"""Payment Service.

This is the service that carries the Phase 1 defect. In healthy mode it
performs a short database round-trip per payment. When the fault mode
``db_conn_leak`` is activated, every request leaks one pooled connection,
which gradually exhausts the pool until acquisition times out. That single
injected defect is what produces the reproducible incident:

    payment latency rises -> payments fail -> order requests fail
    -> api-gateway returns HTTP 500
"""

from __future__ import annotations

import logging
import threading
import uuid

from fastapi import HTTPException

from common import db
from common.bootstrap import create_app
from common.config import get_settings
from common.errors import DatabaseError
from common.metrics import APP_ERRORS_TOTAL
from common.models import FaultStatus, FaultUpdate, HealthResponse, PaymentRequest, PaymentResponse

SERVICE_NAME = "payment-service"

app = create_app(
    SERVICE_NAME,
    title="TraceMind Payment Service",
    description="Processes payments against PostgreSQL and hosts the Phase 1 fault switch.",
)

logger = logging.getLogger(__name__)

_FAULT_VALID_MODES = {"none", "db_conn_leak"}

_fault_lock = threading.Lock()
_fault_mode = get_settings().payment_fault_mode

_leaked_lock = threading.Lock()
_leaked_connections: list = []


def get_fault_mode() -> str:
    with _fault_lock:
        return _fault_mode


def set_fault_mode(mode: str) -> str:
    if mode not in _FAULT_VALID_MODES:
        raise ValueError(f"unsupported fault mode: {mode!r}")
    global _fault_mode
    with _fault_lock:
        previous, _fault_mode = _fault_mode, mode
    logger.warning(
        "Payment fault mode changed",
        extra={"event_type": "FAULT_MODE_CHANGE", "previous_mode": previous, "mode": mode},
    )
    return previous


def leaked_connection_count() -> int:
    with _leaked_lock:
        return len(_leaked_connections)


def _leak_connection() -> None:
    """Acquire a pooled connection and deliberately never release it."""

    pool = db.get_pool(SERVICE_NAME)
    conn = pool.acquire()
    with _leaked_lock:
        _leaked_connections.append(conn)
    logger.warning(
        "Leaked a database connection (simulated defect)",
        extra={"event_type": "DB_CONNECTION_LEAK", "leaked_connections": leaked_connection_count()},
    )


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:  # pragma: no cover - trivial
    db_ok = db.check_health(SERVICE_NAME)
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        service=SERVICE_NAME,
        database_ok=db_ok,
        detail=None if db_ok else "database connection unavailable",
    )


@app.post("/pay", response_model=PaymentResponse)
async def pay(request: PaymentRequest) -> PaymentResponse:
    mode = get_fault_mode()

    if mode == "db_conn_leak":
        try:
            _leak_connection()
        except DatabaseError as exc:
            _record_db_error("Database connection leak blocked: pool exhausted", str(exc))

    try:
        with db.connection(SERVICE_NAME) as conn:
            conn.execute("SELECT 1")
    except DatabaseError as exc:
        _record_db_error("Database connection acquisition timeout", str(exc))
        raise HTTPException(status_code=503, detail="database connection acquisition timeout")

    payment_id = f"pay-{uuid.uuid4().hex[:12]}"
    logger.info(
        "Payment approved",
        extra={"event_type": "PAYMENT_APPROVED", "order_id": request.order_id, "payment_id": payment_id},
    )
    return PaymentResponse(payment_id=payment_id, status="APPROVED", order_id=request.order_id)


def _record_db_error(message: str, detail: str) -> None:
    APP_ERRORS_TOTAL.labels(SERVICE_NAME, "DATABASE_ERROR").inc()
    logger.error(
        message,
        extra={"event_type": "DATABASE_ERROR", "detail": detail},
    )


@app.get("/admin/fault", response_model=FaultStatus)
async def read_fault() -> FaultStatus:
    mode = get_fault_mode()
    return FaultStatus(
        service=SERVICE_NAME,
        mode=mode,
        active=mode != "none",
        leaked_connections=leaked_connection_count(),
    )


@app.post("/admin/fault", response_model=FaultStatus)
async def update_fault(update: FaultUpdate) -> FaultStatus:
    try:
        set_fault_mode(update.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    mode = get_fault_mode()
    return FaultStatus(
        service=SERVICE_NAME,
        mode=mode,
        active=mode != "none",
        leaked_connections=leaked_connection_count(),
    )


@app.post("/admin/reset", response_model=FaultStatus)
async def reset_fault() -> FaultStatus:
    """Return the service to a healthy state and release leaked connections."""

    pool = db.get_pool(SERVICE_NAME)
    with _leaked_lock:
        leaked = list(_leaked_connections)
        _leaked_connections.clear()
    for conn in leaked:
        try:
            pool.release(conn)
        except Exception:  # pragma: no cover - defensive
            pass
    set_fault_mode("none")
    logger.warning("Payment service reset to healthy state", extra={"event_type": "FAULT_RESET"})
    return FaultStatus(service=SERVICE_NAME, mode="none", active=False, leaked_connections=0)
