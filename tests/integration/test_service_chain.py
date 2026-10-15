"""End-to-end test of the incident propagation path.

Starts all four services in-process (uvicorn), drives traffic through the
API Gateway, injects the payment-service defect, and asserts that the
failure propagates to an HTTP 500 at the gateway and then recovers.
"""

from __future__ import annotations

import os
import socket
import threading
import time

import httpx
import pytest
import uvicorn

GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", "18100"))
ORDER_PORT = int(os.environ.get("ORDER_PORT", "18101"))
PAYMENT_PORT = int(os.environ.get("PAYMENT_PORT", "18102"))
USER_PORT = int(os.environ.get("USER_PORT", "18103"))

GATEWAY_URL = f"http://127.0.0.1:{GATEWAY_PORT}"
PAYMENT_ADMIN_URL = f"http://127.0.0.1:{PAYMENT_PORT}"


def _wait_for_port(port: int, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.1)
    return False


@pytest.fixture(scope="module")
def running_stack():
    from services.api_gateway.app import app as gateway_app
    from services.order_service.app import app as order_app
    from services.payment_service.app import app as payment_app
    from services.user_service.app import app as user_app

    plan = [
        (user_app, USER_PORT),
        (payment_app, PAYMENT_PORT),
        (order_app, ORDER_PORT),
        (gateway_app, GATEWAY_PORT),
    ]

    servers = []
    threads = []
    for app_obj, port in plan:
        server = uvicorn.Server(
            uvicorn.Config(app_obj, host="127.0.0.1", port=port, log_level="warning")
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        servers.append(server)
        threads.append(thread)

    for _, port in plan:
        assert _wait_for_port(port), f"service on port {port} did not start"

    yield

    for server in servers:
        server.should_exit = True
    for thread in threads:
        thread.join(timeout=5)


def test_incident_propagates_and_recovers(running_stack):
    with httpx.Client(timeout=10.0) as client:
        client.post(f"{PAYMENT_ADMIN_URL}/admin/reset")

        healthy = client.post(
            f"{GATEWAY_URL}/orders", json={"user_id": "user-1", "amount": 10.0}
        )
        assert healthy.status_code == 200
        assert healthy.json()["status"] == "CONFIRMED"

        fault = client.post(
            f"{PAYMENT_ADMIN_URL}/admin/fault", json={"mode": "db_conn_leak"}
        )
        assert fault.status_code == 200

        saw_gateway_500 = False
        for _ in range(40):
            response = client.post(
                f"{GATEWAY_URL}/orders", json={"user_id": "user-1", "amount": 10.0}
            )
            if response.status_code == 500:
                saw_gateway_500 = True
                break
        assert saw_gateway_500, "gateway never surfaced HTTP 500 during the incident"

        client.post(f"{PAYMENT_ADMIN_URL}/admin/reset")

        recovered = client.post(
            f"{GATEWAY_URL}/orders", json={"user_id": "user-2", "amount": 10.0}
        )
        assert recovered.status_code == 200
