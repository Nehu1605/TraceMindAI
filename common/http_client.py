"""Helpers for synchronous-style downstream HTTP calls with error mapping."""

from __future__ import annotations

from typing import Any

import httpx

from .config import get_settings
from .errors import DownstreamServiceError


def new_client(timeout: float | None = None) -> httpx.AsyncClient:
    """Create an ``httpx.AsyncClient`` using the configured timeout."""

    settings = get_settings()
    return httpx.AsyncClient(timeout=timeout or settings.http_timeout_seconds)


def _raise_for_downstream(service: str, response: httpx.Response) -> None:
    if response.status_code >= 500:
        raise DownstreamServiceError(service, response.status_code, response.text[:500])
    if response.status_code >= 400:
        raise DownstreamServiceError(service, response.status_code, response.text[:500])


async def request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    service: str,
    json: dict[str, Any] | None = None,
) -> Any:
    """Issue a request and return parsed JSON, raising on downstream errors."""

    try:
        response = await client.request(method, url, json=json)
    except httpx.HTTPError as exc:
        raise DownstreamServiceError(service, 0, str(exc)) from exc
    _raise_for_downstream(service, response)
    if response.content:
        return response.json()
    return None
