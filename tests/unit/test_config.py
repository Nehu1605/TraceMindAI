from __future__ import annotations

from common.config import Settings, get_settings, reset_settings_cache


def test_defaults_are_safe():
    settings = Settings()
    assert settings.db_backend in {"postgres", "simulated"}
    assert settings.payment_fault_mode == "none"
    assert settings.is_payment_fault_active() is False


def test_environment_overrides(monkeypatch):
    monkeypatch.setenv("DB_POOL_SIZE", "7")
    monkeypatch.setenv("PAYMENT_FAULT_MODE", "db_conn_leak")
    reset_settings_cache()

    settings = get_settings()
    assert settings.db_pool_size == 7
    assert settings.is_payment_fault_active() is True

    reset_settings_cache()
