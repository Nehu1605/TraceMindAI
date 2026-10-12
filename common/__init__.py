"""Shared building blocks for the TraceMind AI demo microservices.

Phase 1 scope: a controllable distributed system that emits observable
traces, structured logs, and metrics, and that can reproduce a single
well-understood incident (database connection exhaustion in payment-service).
"""

__all__ = [
    "config",
    "logging_config",
    "telemetry",
    "metrics",
    "db",
    "http_client",
    "errors",
]
