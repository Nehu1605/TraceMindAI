from __future__ import annotations

import pytest

from common import db
from common.config import reset_settings_cache
from common.errors import PoolExhaustedError


def test_pool_exhaustion_and_release(monkeypatch):
    monkeypatch.setenv("DB_POOL_SIZE", "2")
    monkeypatch.setenv("DB_POOL_TIMEOUT_SECONDS", "0.2")
    monkeypatch.setenv("DB_BACKEND", "simulated")
    reset_settings_cache()
    db.reset_pool()

    pool = db.get_pool("test-service")
    assert pool.size == 2

    first = pool.acquire()
    second = pool.acquire()
    assert pool.in_use == 2

    with pytest.raises(PoolExhaustedError):
        pool.acquire()

    pool.release(first)
    third = pool.acquire()
    assert pool.in_use == 2

    pool.release(second)
    pool.release(third)
    assert pool.in_use == 0

    db.reset_pool("test-service")
    reset_settings_cache()


def test_connection_context_manager_releases(monkeypatch):
    monkeypatch.setenv("DB_POOL_SIZE", "1")
    monkeypatch.setenv("DB_BACKEND", "simulated")
    reset_settings_cache()
    db.reset_pool()

    with db.connection("ctx-service") as conn:
        assert conn.execute("SELECT 1")

    pool = db.get_pool("ctx-service")
    assert pool.in_use == 0
    assert db.check_health("ctx-service") is True

    db.reset_pool("ctx-service")
    reset_settings_cache()
