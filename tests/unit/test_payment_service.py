from __future__ import annotations

from fastapi.testclient import TestClient

from common import db
from common.config import reset_settings_cache
from services.payment_service.app import app as payment_app

PAYMENT = {"order_id": "ord-test", "user_id": "user-1", "amount": 12.5, "currency": "USD"}


def test_payment_succeeds_when_healthy(monkeypatch):
    monkeypatch.setenv("DB_POOL_SIZE", "3")
    monkeypatch.setenv("DB_POOL_TIMEOUT_SECONDS", "0.2")
    reset_settings_cache()
    db.reset_pool()

    with TestClient(payment_app) as client:
        assert client.post("/admin/reset").status_code == 200
        response = client.post("/pay", json=PAYMENT)
        assert response.status_code == 200
        assert response.json()["status"] == "APPROVED"

    db.reset_pool()
    reset_settings_cache()


def test_db_conn_leak_eventually_fails_payments(monkeypatch):
    monkeypatch.setenv("DB_POOL_SIZE", "2")
    monkeypatch.setenv("DB_POOL_TIMEOUT_SECONDS", "0.2")
    reset_settings_cache()
    db.reset_pool()

    with TestClient(payment_app) as client:
        client.post("/admin/reset")

        fault = client.post("/admin/fault", json={"mode": "db_conn_leak"}).json()
        assert fault["active"] is True
        assert fault["mode"] == "db_conn_leak"

        statuses = [client.post("/pay", json=PAYMENT).status_code for _ in range(8)]
        assert 200 in statuses
        assert 503 in statuses

        reset = client.post("/admin/reset").json()
        assert reset["active"] is False
        assert reset["leaked_connections"] == 0

        assert client.post("/pay", json=PAYMENT).status_code == 200

    db.reset_pool()
    reset_settings_cache()


def test_invalid_fault_mode_rejected(monkeypatch):
    reset_settings_cache()
    db.reset_pool()
    with TestClient(payment_app) as client:
        response = client.post("/admin/fault", json={"mode": "not-a-mode"})
        assert response.status_code == 400
    db.reset_pool()
    reset_settings_cache()
