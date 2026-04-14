"""Shared HTTP helpers for polite public-data scraping."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx


DEFAULT_REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_REQUEST_DELAY_SECONDS = 0.35
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 0.75
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "dev-rse/1.0 (+https://github.com/chrisj909/dev-rse)",
}


def _parse_retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None

    text = value.strip()
    if not text:
        return None

    try:
        return max(float(text), 0.0)
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(text)
        now = datetime.now(tz=retry_at.tzinfo or timezone.utc)
        return max((retry_at - now).total_seconds(), 0.0)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def _compute_backoff_seconds(response: httpx.Response | None, attempt_index: int) -> float:
    retry_after = None
    if response is not None:
        retry_after = _parse_retry_after_seconds(response.headers.get("Retry-After"))
    if retry_after is not None:
        return retry_after
    return DEFAULT_BACKOFF_SECONDS * (2 ** attempt_index)


async def polite_get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any],
    headers: dict[str, str] | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> Any:
    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}

    last_response: httpx.Response | None = None
    for attempt in range(max_retries):
        try:
            response = await client.get(url, params=params, headers=merged_headers)
            last_response = response

            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt == max_retries - 1:
                    response.raise_for_status()
                await asyncio.sleep(_compute_backoff_seconds(response, attempt))
                continue

            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and "error" in data:
                error = data["error"]
                error_code = error.get("code") if isinstance(error, dict) else None
                if error_code in RETRYABLE_STATUS_CODES and attempt < max_retries - 1:
                    await asyncio.sleep(_compute_backoff_seconds(response, attempt))
                    continue
                raise RuntimeError(f"ArcGIS API error: {error}")
            return data
        except (httpx.NetworkError, httpx.TimeoutException, httpx.RemoteProtocolError):
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(DEFAULT_BACKOFF_SECONDS * (2 ** attempt))

    if last_response is not None:
        last_response.raise_for_status()
    raise RuntimeError(f"Failed to fetch JSON from {url}")


async def polite_page_pause(delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS) -> None:
    await asyncio.sleep(delay_seconds)