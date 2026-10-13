"""Centralized, environment-driven configuration for all demo services."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings shared by every TraceMind demo service.

    Values are read from environment variables (case-insensitive) and,
    when present, an optional ``.env`` file. Every setting has a safe
    default so the demo runs out of the box with Docker Compose.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Identity -------------------------------------------------------
    service_name: str = "tracemind-service"
    environment: str = "local"
    log_level: str = "INFO"

    # --- Database -------------------------------------------------------
    # "postgres" uses a real PostgreSQL pool; "simulated" uses an in-process
    # pool so tests and local runs work without a database.
    db_backend: str = "postgres"
    database_url: str = Field(
        default="postgresql://tracemind:tracemind@localhost:5432/tracemind"
    )
    db_pool_size: int = 5
    # Seconds to wait for a free connection before raising a timeout.
    db_pool_timeout_seconds: float = 2.0
    # Simulated per-query latency ceiling, keeps the demo fast.
    db_query_latency_ms: int = 10

    # --- Inter-service HTTP --------------------------------------------
    order_service_url: str = "http://localhost:8001"
    payment_service_url: str = "http://localhost:8002"
    user_service_url: str = "http://localhost:8003"
    http_timeout_seconds: float = 5.0

    # --- Fault injection (payment-service) ------------------------------
    # "none"          -> healthy behavior
    # "db_conn_leak"  -> each request leaks a pooled connection (Phase 1 bug)
    payment_fault_mode: str = "none"

    # --- Telemetry ------------------------------------------------------
    otel_enabled: bool = True
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    prometheus_enabled: bool = True

    # --- Ingestion / normalization (Phase 2) ----------------------------
    # Tolerance used when ordering events whose clocks may differ slightly.
    event_time_tolerance_ms: int = 200
    # Events whose ingestion lag exceeds this are flagged (kept, not dropped).
    late_event_threshold_seconds: float = 60.0
    # event_time > ingestion_time by more than this suggests clock skew.
    clock_skew_threshold_ms: int = 500
    # Window within which identical events are treated as duplicates.
    dedup_window_seconds: float = 300.0

    # --- Correlation / graph (Phase 3) ----------------------------------
    # Max gap (s) between a log and a candidate span for an inferred link.
    correlation_window_seconds: float = 30.0
    # Max gap (s) between alerts that may be grouped into one incident.
    alert_group_window_seconds: float = 300.0
    # Alerts may be grouped across services up to this many CALLS hops.
    alert_group_max_hops: int = 2
    # Sliding-window size/step (s) for streaming-style correlation (I7).
    sliding_window_seconds: float = 300.0
    sliding_window_step_seconds: float = 60.0

    def is_payment_fault_active(self) -> bool:
        return self.payment_fault_mode not in ("", "none")


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""

    return Settings()


def reset_settings_cache() -> None:
    """Clear the cached settings (used by tests and scenario switches)."""

    get_settings.cache_clear()
