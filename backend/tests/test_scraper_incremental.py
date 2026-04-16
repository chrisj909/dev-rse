from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.scrapers.arcgis_scraper import COUNTY_CONFIGS, _build_where_clause
from app.scrapers import run_all_scrapers_with_metadata


def test_build_where_clause_uses_shelby_updated_field_for_incremental_runs():
    updated_since = datetime(2026, 4, 13, 0, 0, 0, tzinfo=timezone.utc)

    where_clause = _build_where_clause(COUNTY_CONFIGS["shelby"], updated_since)

    assert COUNTY_CONFIGS["shelby"]["default_where"] in where_clause
    assert "Transcreate_Save" in where_clause
    assert "DATE '2026-04-13 00:00:00'" in where_clause


def test_build_where_clause_treats_naive_timestamps_as_utc():
    updated_since = datetime(2026, 4, 13, 6, 30, 0)

    where_clause = _build_where_clause(COUNTY_CONFIGS["shelby"], updated_since)

    assert "DATE '2026-04-13 06:30:00'" in where_clause


def test_build_where_clause_falls_back_when_county_has_no_incremental_field():
    updated_since = datetime(2026, 4, 13, 0, 0, 0, tzinfo=timezone.utc)

    where_clause = _build_where_clause(COUNTY_CONFIGS["jefferson"], updated_since)

    assert where_clause == COUNTY_CONFIGS["jefferson"]["default_where"]


@pytest.mark.asyncio
async def test_run_all_scrapers_with_metadata_uses_arcgis_count_for_pagination(monkeypatch):
    async def fake_arcgis_fetch_all(*, limit=None, updated_since=None, start_offset=0):
        assert limit == 1000
        assert start_offset == 5000
        return [
            {"county": "shelby", "parcel_id": "A"},
            {"county": "shelby", "parcel_id": "B"},
        ]

    async def fake_govease_fetch_all(*, updated_since=None):
        return [
            {"county": "shelby", "parcel_id": "A", "raw_data": {"source": "govease"}},
            {"county": "shelby", "parcel_id": "C", "raw_data": {"source": "govease"}},
        ]

    monkeypatch.setattr(
        "app.scrapers.ArcGISScraper",
        lambda county: SimpleNamespace(fetch_all=fake_arcgis_fetch_all),
    )
    monkeypatch.setattr(
        "app.scrapers.GovEaseScraper",
        lambda county: SimpleNamespace(fetch_all=fake_govease_fetch_all),
    )

    result = await run_all_scrapers_with_metadata(limit=1000, county="shelby", start_offset=5000)

    assert result["primary_fetched"] == 2
    assert result["records"] == [
        {"county": "shelby", "parcel_id": "A"},
        {"county": "shelby", "parcel_id": "B"},
    ]


@pytest.mark.asyncio
async def test_run_all_scrapers_with_metadata_applies_govease_overlay_once(monkeypatch):
    async def fake_arcgis_fetch_all(*, limit=None, updated_since=None, start_offset=0):
        return [{"county": "shelby", "parcel_id": "A", "raw_data": {}}]

    async def fake_govease_fetch_all(*, updated_since=None):
        return [{"county": "shelby", "parcel_id": "A", "raw_data": {"source": "govease"}}]

    monkeypatch.setattr(
        "app.scrapers.ArcGISScraper",
        lambda county: SimpleNamespace(fetch_all=fake_arcgis_fetch_all),
    )
    monkeypatch.setattr(
        "app.scrapers.GovEaseScraper",
        lambda county: SimpleNamespace(fetch_all=fake_govease_fetch_all),
    )

    result = await run_all_scrapers_with_metadata(limit=1000, county="shelby", start_offset=0)

    assert result["primary_fetched"] == 1
    assert result["records"] == [
        {
            "county": "shelby",
            "parcel_id": "A",
            "raw_data": {"govease": {"source": "govease"}},
            "is_tax_delinquent": True,
        }
    ]