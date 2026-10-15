"""Simple load generator that drives traffic through the API Gateway.

The generator intentionally records only what an operator could observe
from the outside (status codes and latency); it never reads the injected
cause. That keeps the synthetic ground truth separate from RCA inputs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

DEFAULT_USER_IDS = ("user-1", "user-2", "user-3")


@dataclass
class TrafficStats:
    total: int = 0
    success: int = 0
    client_errors: int = 0
    server_errors: int = 0
    transport_errors: int = 0
    total_latency_s: float = 0.0
    max_latency_s: float = 0.0
    status_counts: dict[str, int] = field(default_factory=dict)

    def record(self, status: int, latency_s: float) -> None:
        self.total += 1
        self.total_latency_s += latency_s
        self.max_latency_s = max(self.max_latency_s, latency_s)
        key = str(status)
        self.status_counts[key] = self.status_counts.get(key, 0) + 1
        if status == 0:
            self.transport_errors += 1
        elif 200 <= status < 300:
            self.success += 1
        elif 500 <= status < 600:
            self.server_errors += 1
        elif 400 <= status < 500:
            self.client_errors += 1

    @property
    def avg_latency_ms(self) -> float:
        return (self.total_latency_s / self.total * 1000.0) if self.total else 0.0

    @property
    def error_rate(self) -> float:
        if not self.total:
            return 0.0
        return (self.server_errors + self.transport_errors) / self.total

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "success": self.success,
            "server_errors": self.server_errors,
            "client_errors": self.client_errors,
            "transport_errors": self.transport_errors,
            "error_rate": round(self.error_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "max_latency_ms": round(self.max_latency_s * 1000.0, 2),
            "status_counts": self.status_counts,
        }


def send_order(
    client: httpx.Client,
    gateway_url: str,
    user_id: str = "user-1",
    amount: float = 10.0,
) -> tuple[int, float]:
    payload = {"user_id": user_id, "amount": amount, "currency": "USD"}
    start = time.perf_counter()
    try:
        response = client.post(f"{gateway_url}/orders", json=payload)
        status = response.status_code
    except httpx.HTTPError:
        status = 0
    return status, time.perf_counter() - start


def run_traffic(
    gateway_url: str,
    duration_seconds: float,
    requests_per_second: float = 5.0,
    timeout_seconds: float = 5.0,
    stop_on_error: bool = False,
    max_requests: int = 100000,
    user_ids: tuple[str, ...] = DEFAULT_USER_IDS,
) -> TrafficStats:
    """Send requests for a bounded duration and return aggregate stats."""

    stats = TrafficStats()
    interval = 1.0 / requests_per_second if requests_per_second > 0 else 0.0
    deadline = time.monotonic() + duration_seconds
    index = 0

    with httpx.Client(timeout=timeout_seconds) as client:
        while time.monotonic() < deadline and stats.total < max_requests:
            loop_start = time.monotonic()
            status, latency = send_order(client, gateway_url, user_ids[index % len(user_ids)])
            stats.record(status, latency)
            index += 1
            if stop_on_error and (status == 0 or status >= 500):
                break
            remaining = interval - (time.monotonic() - loop_start)
            if remaining > 0:
                time.sleep(remaining)

    return stats
