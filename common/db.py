"""Database connection pooling with a swappable backend.

Two backends are provided:

* ``postgres``  - a real ``psycopg2`` threaded connection pool.
* ``simulated`` - an in-process pool with identical semantics, used by
  tests and by ``DB_BACKEND=simulated`` runs so the demo works without a
  live database.

Both backends enforce a bounded pool size and a bounded acquisition
timeout, which is what lets the primary Phase 1 incident (connection
exhaustion) be reproduced deterministically.
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Iterator

from . import metrics
from .config import Settings, get_settings
from .errors import DatabaseError, DatabaseTimeoutError, PoolExhaustedError

logger = logging.getLogger(__name__)


class Connection(ABC):
    """Minimal connection interface used by the demo services."""

    @abstractmethod
    def execute(self, statement: str, params: tuple | None = None) -> list[tuple]:
        ...


class BasePool(ABC):
    def __init__(self, size: int, acquire_timeout: float, service_name: str) -> None:
        self.size = size
        self.acquire_timeout = acquire_timeout
        self.service_name = service_name
        self._in_use = 0
        self._lock = threading.Lock()
        metrics.DB_POOL_SIZE_GAUGE.labels(service_name).set(size)
        metrics.DB_CONNECTIONS_IN_USE.labels(service_name).set(0)

    @property
    def in_use(self) -> int:
        with self._lock:
            return self._in_use

    def _try_acquire_slot(self) -> bool:
        with self._lock:
            if self._in_use < self.size:
                self._in_use += 1
                metrics.DB_CONNECTIONS_IN_USE.labels(self.service_name).set(self._in_use)
                return True
            return False

    def _release_slot(self) -> None:
        with self._lock:
            if self._in_use > 0:
                self._in_use -= 1
            metrics.DB_CONNECTIONS_IN_USE.labels(self.service_name).set(self._in_use)

    def acquire(self) -> Connection:
        deadline = time.monotonic() + self.acquire_timeout
        while True:
            if self._try_acquire_slot():
                try:
                    return self._open_connection()
                except Exception:
                    self._release_slot()
                    raise
            if time.monotonic() >= deadline:
                metrics.DB_CONNECTION_ERRORS_TOTAL.labels(self.service_name).inc()
                raise PoolExhaustedError(
                    f"database connection acquisition timeout after "
                    f"{self.acquire_timeout:.2f}s (pool size={self.size}, in_use={self.in_use})"
                )
            time.sleep(0.01)

    def release(self, connection: Connection) -> None:
        try:
            self._close_connection(connection)
        finally:
            self._release_slot()

    @abstractmethod
    def _open_connection(self) -> Connection:
        ...

    @abstractmethod
    def _close_connection(self, connection: Connection) -> None:
        ...

    def close(self) -> None:  # pragma: no cover - trivial
        pass


class _SimulatedConnection(Connection):
    def __init__(self, latency_ms: int) -> None:
        self.latency_ms = latency_ms

    def execute(self, statement: str, params: tuple | None = None) -> list[tuple]:
        if self.latency_ms:
            time.sleep(self.latency_ms / 1000.0)
        return [(1,)]


class SimulatedPool(BasePool):
    """In-process pool that mirrors the real pool's exhaustion behavior."""

    def __init__(self, size: int, acquire_timeout: float, service_name: str, latency_ms: int = 10) -> None:
        super().__init__(size, acquire_timeout, service_name)
        self.latency_ms = latency_ms

    def _open_connection(self) -> Connection:
        return _SimulatedConnection(self.latency_ms)

    def _close_connection(self, connection: Connection) -> None:
        return None


class _PostgresConnection(Connection):
    def __init__(self, raw, pool: "PostgresPool") -> None:
        self._raw = raw
        self._pool = pool

    @property
    def raw(self):
        return self._raw

    def execute(self, statement: str, params: tuple | None = None) -> list[tuple]:
        try:
            with self._raw.cursor() as cursor:
                cursor.execute(statement, params)
                if cursor.description is None:
                    self._raw.commit()
                    return []
                return cursor.fetchall()
        except Exception as exc:  # pragma: no cover - needs a live DB
            self._raw.rollback()
            raise DatabaseTimeoutError(str(exc)) from exc


class PostgresPool(BasePool):
    """Thin wrapper around ``psycopg2.pool.ThreadedConnectionPool``."""

    def __init__(self, url: str, size: int, acquire_timeout: float, service_name: str) -> None:
        super().__init__(size, acquire_timeout, service_name)
        import psycopg2.pool  # imported lazily so simulated mode needs no driver

        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=size, dsn=url
        )

    def _open_connection(self) -> Connection:
        raw = self._pool.getconn()
        return _PostgresConnection(raw, self)

    def _close_connection(self, connection: Connection) -> None:
        self._pool.putconn(connection.raw)

    def close(self) -> None:  # pragma: no cover - needs a live DB
        self._pool.closeall()


_pool_lock = threading.Lock()
_pools: dict[str, BasePool] = {}


def build_pool(settings: Settings | None = None, service_name: str | None = None) -> BasePool:
    settings = settings or get_settings()
    name = service_name or settings.service_name
    if settings.db_backend == "simulated":
        return SimulatedPool(
            size=settings.db_pool_size,
            acquire_timeout=settings.db_pool_timeout_seconds,
            service_name=name,
            latency_ms=settings.db_query_latency_ms,
        )
    return PostgresPool(
        url=settings.database_url,
        size=settings.db_pool_size,
        acquire_timeout=settings.db_pool_timeout_seconds,
        service_name=name,
    )


def get_pool(service_name: str | None = None) -> BasePool:
    """Return the pool for a service, creating it on first use."""

    settings = get_settings()
    name = service_name or settings.service_name
    with _pool_lock:
        if name not in _pools:
            _pools[name] = build_pool(settings, name)
        return _pools[name]


def reset_pool(service_name: str | None = None) -> None:
    """Drop one (or all) module-level pools (used by tests)."""

    with _pool_lock:
        keys = [service_name] if service_name else list(_pools)
        for key in keys:
            pool = _pools.pop(key, None)
            if pool is not None:
                try:
                    pool.close()
                except Exception:  # pragma: no cover - defensive
                    pass


@contextmanager
def connection(service_name: str | None = None) -> Iterator[Connection]:
    """Context manager that acquires and always releases a connection."""

    pool = get_pool(service_name)
    conn = pool.acquire()
    try:
        yield conn
    finally:
        pool.release(conn)


def check_health(service_name: str | None = None) -> bool:
    """Return ``True`` when a connection can be acquired and used."""

    try:
        with connection(service_name) as conn:
            conn.execute("SELECT 1")
        return True
    except DatabaseError:
        return False
