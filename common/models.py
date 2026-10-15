"""Shared request/response models for the demo microservices."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    database_ok: bool = True
    detail: str | None = None


class OrderRequest(BaseModel):
    user_id: str = Field(default="user-1")
    amount: float = Field(default=10.0, gt=0)
    currency: str = Field(default="USD")


class OrderResponse(BaseModel):
    order_id: str
    status: str
    user_id: str
    amount: float
    currency: str
    payment_id: str | None = None


class PaymentRequest(BaseModel):
    order_id: str
    user_id: str
    amount: float
    currency: str = "USD"


class PaymentResponse(BaseModel):
    payment_id: str
    status: str
    order_id: str


class UserResponse(BaseModel):
    user_id: str
    name: str
    tier: str


class FaultUpdate(BaseModel):
    mode: str = Field(description="One of: none, db_conn_leak")


class FaultStatus(BaseModel):
    service: str
    mode: str
    active: bool
    leaked_connections: int
