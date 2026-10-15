"""Shared test configuration.

Environment variables are set *before* any service module is imported so the
test suite runs against the simulated database backend and without trying to
export traces to a collector.
"""

from __future__ import annotations

import os

os.environ.setdefault("DB_BACKEND", "simulated")
os.environ.setdefault("OTEL_ENABLED", "false")
os.environ.setdefault("PROMETHEUS_ENABLED", "true")
os.environ.setdefault("DB_POOL_SIZE", "3")
os.environ.setdefault("DB_POOL_TIMEOUT_SECONDS", "0.3")
os.environ.setdefault("PAYMENT_FAULT_MODE", "none")

ORDER_PORT = 18101
PAYMENT_PORT = 18102
USER_PORT = 18103
GATEWAY_PORT = 18100

os.environ.setdefault("ORDER_PORT", str(ORDER_PORT))
os.environ.setdefault("PAYMENT_PORT", str(PAYMENT_PORT))
os.environ.setdefault("USER_PORT", str(USER_PORT))
os.environ.setdefault("GATEWAY_PORT", str(GATEWAY_PORT))

os.environ.setdefault("ORDER_SERVICE_URL", f"http://127.0.0.1:{ORDER_PORT}")
os.environ.setdefault("PAYMENT_SERVICE_URL", f"http://127.0.0.1:{PAYMENT_PORT}")
os.environ.setdefault("USER_SERVICE_URL", f"http://127.0.0.1:{USER_PORT}")

import pytest  # noqa: E402

from common import db  # noqa: E402
from common.config import reset_settings_cache  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_pools():
    reset_settings_cache()
    db.reset_pool()
    yield
    db.reset_pool()
    reset_settings_cache()
