"""Domain errors for the demo services."""

from __future__ import annotations


class TraceMindError(Exception):
    """Base class for all TraceMind domain errors."""


class DatabaseError(TraceMindError):
    """Generic database failure."""


class PoolExhaustedError(DatabaseError):
    """No database connection became available before the timeout expired."""


class DatabaseTimeoutError(DatabaseError):
    """A query exceeded the configured execution timeout."""


class DownstreamServiceError(TraceMindError):
    """A downstream service returned an unexpected response."""

    def __init__(self, service: str, status_code: int, detail: str = "") -> None:
        super().__init__(f"{service} returned {status_code}: {detail}")
        self.service = service
        self.status_code = status_code
        self.detail = detail
