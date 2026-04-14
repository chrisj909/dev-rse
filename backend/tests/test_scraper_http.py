from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from app.scrapers.http_utils import polite_get_json, polite_page_pause


def _response(status_code: int, payload: object, headers: dict[str, str] | None = None) -> httpx.Response:
    request = httpx.Request("GET", "https://example.com/data")
    return httpx.Response(status_code=status_code, json=payload, headers=headers, request=request)


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def get(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.asyncio
async def test_polite_get_json_retries_429_then_succeeds(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("app.scrapers.http_utils.asyncio.sleep", sleep)

    client = FakeClient(
        [
            _response(429, {"detail": "slow down"}, headers={"Retry-After": "0"}),
            _response(200, {"features": []}),
        ]
    )

    data = await polite_get_json(client, "https://example.com/data", params={"page": 1})

    assert data == {"features": []}
    assert len(client.calls) == 2
    sleep.assert_awaited_once()
    assert client.calls[0]["headers"]["User-Agent"].startswith("dev-rse/")


@pytest.mark.asyncio
async def test_polite_get_json_retries_network_error_then_succeeds(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("app.scrapers.http_utils.asyncio.sleep", sleep)

    client = FakeClient(
        [
            httpx.NetworkError("temporary failure"),
            _response(200, {"properties": []}),
        ]
    )

    data = await polite_get_json(client, "https://example.com/data", params={"page": 1})

    assert data == {"properties": []}
    assert len(client.calls) == 2
    sleep.assert_awaited_once()


@pytest.mark.asyncio
async def test_polite_get_json_raises_after_retryable_status_exhausted(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("app.scrapers.http_utils.asyncio.sleep", sleep)

    client = FakeClient([
        _response(503, {"detail": "busy"}),
        _response(503, {"detail": "busy"}),
        _response(503, {"detail": "busy"}),
    ])

    with pytest.raises(httpx.HTTPStatusError):
        await polite_get_json(client, "https://example.com/data", params={"page": 1})

    assert len(client.calls) == 3
    assert sleep.await_count == 2


@pytest.mark.asyncio
async def test_polite_page_pause_waits(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("app.scrapers.http_utils.asyncio.sleep", sleep)

    await polite_page_pause(0.2)

    sleep.assert_awaited_once_with(0.2)