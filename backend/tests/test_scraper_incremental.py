from __future__ import annotations

from datetime import datetime, timezone

from app.scrapers.arcgis_scraper import COUNTY_CONFIGS, _build_where_clause


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