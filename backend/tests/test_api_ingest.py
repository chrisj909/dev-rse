from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from fastapi import HTTPException

from app.api.ingest import _resolve_updated_since


def test_resolve_updated_since_rejects_conflicting_params():
    updated_since = datetime(2026, 4, 13, 0, 0, tzinfo=timezone.utc)

    try:
        _resolve_updated_since(updated_since, 1)
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "Pass either updated_since or delta_days, not both."
    else:
        raise AssertionError("Expected HTTPException for conflicting incremental parameters")


def test_resolve_updated_since_normalizes_naive_datetime_to_utc():
    updated_since = datetime(2026, 4, 13, 0, 0, 0)

    resolved = _resolve_updated_since(updated_since, None)

    assert resolved == datetime(2026, 4, 13, 0, 0, 0, tzinfo=timezone.utc)


def test_resolve_updated_since_supports_delta_days_window():
    lower_bound = datetime.now(tz=timezone.utc) - timedelta(days=2, seconds=1)

    resolved = _resolve_updated_since(None, 2)

    upper_bound = datetime.now(tz=timezone.utc) - timedelta(days=2) + timedelta(seconds=1)
    assert resolved is not None
    assert lower_bound <= resolved <= upper_bound


def test_ingest_route_rejects_incremental_delinquent_only_runs(test_client, monkeypatch):
    monkeypatch.setattr("app.api.ingest.settings.cron_secret", None)

    resp = test_client.post("/api/ingest/run?delinquent_only=true&delta_days=1")

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Incremental retrieval is not supported for delinquent_only runs."


def test_ingest_route_passes_incremental_cutoff_to_scrapers(test_client, monkeypatch):
    monkeypatch.setattr("app.api.ingest.settings.cron_secret", None)

    captured: dict[str, object] = {}

    async def fake_run_all_scrapers(*, limit=None, county="all", updated_since=None):
        captured["limit"] = limit
        captured["county"] = county
        captured["updated_since"] = updated_since
        return []

    monkeypatch.setattr("app.api.ingest.run_all_scrapers", fake_run_all_scrapers)

    resp = test_client.post("/api/ingest/run?county=shelby&delta_days=1&dry_run=true")

    assert resp.status_code == 200
    assert resp.json()["status"] == "dry_run"
    assert resp.json()["retrieval"]["mode"] == "incremental"
    assert resp.json()["retrieval"]["delta_days"] == 1
    assert captured["county"] == "shelby"
    assert captured["updated_since"] is not None


def test_ingest_route_passes_explicit_updated_since_to_scrapers(test_client, monkeypatch):
    monkeypatch.setattr("app.api.ingest.settings.cron_secret", None)

    captured: dict[str, object] = {}

    async def fake_run_all_scrapers(*, limit=None, county="all", updated_since=None):
        captured["updated_since"] = updated_since
        return []

    monkeypatch.setattr("app.api.ingest.run_all_scrapers", fake_run_all_scrapers)

    resp = test_client.post("/api/ingest/run?dry_run=true&updated_since=2026-04-13T00:00:00Z")

    assert resp.status_code == 200
    assert resp.json()["retrieval"]["updated_since"] == "2026-04-13T00:00:00+00:00"
    assert captured["updated_since"] == datetime(2026, 4, 13, 0, 0, tzinfo=timezone.utc)