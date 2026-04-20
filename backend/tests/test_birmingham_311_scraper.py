"""
Tests for app/scrapers/birmingham_311_scraper.py

Strategy:
  - Mock httpx.AsyncClient to avoid real HTTP calls.
  - Verify pagination, case-type filtering, and address normalization.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.scrapers.birmingham_311_scraper import (
    VIOLATION_CASE_TYPES,
    _build_address,
    fetch_code_violation_addresses,
)


# ── _build_address ────────────────────────────────────────────────────────────

class TestBuildAddress:
    def test_full_record(self):
        rec = {
            "Street Number": "123",
            "Street Direction": "N",
            "Street Name": "Main",
            "Street Type": "St",
        }
        assert _build_address(rec) == "123 N Main St"

    def test_no_direction(self):
        rec = {"Street Number": "456", "Street Name": "Oak", "Street Type": "Ave"}
        assert _build_address(rec) == "456 Oak Ave"

    def test_no_suffix(self):
        rec = {"Street Number": "789", "Street Name": "Elm"}
        assert _build_address(rec) == "789 Elm"

    def test_missing_number_returns_none(self):
        rec = {"Street Name": "Main", "Street Type": "St"}
        assert _build_address(rec) is None

    def test_missing_name_returns_none(self):
        rec = {"Street Number": "100", "Street Type": "St"}
        assert _build_address(rec) is None

    def test_none_values_skipped(self):
        rec = {"Street Number": "10", "Street Direction": None, "Street Name": "Oak", "Street Type": None}
        assert _build_address(rec) == "10 Oak"


# ── fetch_code_violation_addresses ────────────────────────────────────────────

def _make_ckan_response(records: list[dict], success: bool = True) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "success": success,
        "result": {"records": records},
    }
    return mock_resp


class TestFetchCodeViolationAddresses:
    @pytest.mark.asyncio
    async def test_filters_to_violation_case_types(self):
        records = [
            {
                "Case Type": "Dilapidated House or Building",
                "Street Number": "123",
                "Street Name": "Main",
                "Street Type": "ST",
            },
            {
                "Case Type": "Pothole",  # not a violation
                "Street Number": "456",
                "Street Name": "Oak",
                "Street Type": "AVE",
            },
        ]
        client = AsyncMock()
        client.get = AsyncMock(return_value=_make_ckan_response(records))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        result = await fetch_code_violation_addresses(http_client=client)

        assert len(result) == 1
        assert any("123" in addr and "MAIN" in addr for addr in result)

    @pytest.mark.asyncio
    async def test_normalizes_addresses(self):
        records = [
            {
                "Case Type": "Illegal Dumping",
                "Street Number": "500",
                "Street Direction": "North",
                "Street Name": "Elm",
                "Street Type": "Avenue",
            }
        ]
        client = AsyncMock()
        client.get = AsyncMock(return_value=_make_ckan_response(records))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        result = await fetch_code_violation_addresses(http_client=client)

        # normalize_address should upper-case and abbreviate
        assert "500 N ELM AVE" in result

    @pytest.mark.asyncio
    async def test_paginates(self):
        page1 = [
            {"Case Type": "Overgrown Vacant Lot", "Street Number": str(i), "Street Name": "Main", "Street Type": "ST"}
            for i in range(1000)
        ]
        page2 = [
            {"Case Type": "Overgrown Vacant Lot", "Street Number": "1001", "Street Name": "Oak", "Street Type": "AVE"}
        ]

        call_count = 0

        async def fake_get(url, params):
            nonlocal call_count
            call_count += 1
            if params["offset"] == 0:
                return _make_ckan_response(page1)
            return _make_ckan_response(page2)

        client = AsyncMock()
        client.get = fake_get
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        result = await fetch_code_violation_addresses(http_client=client)

        assert call_count == 2
        assert len(result) >= 2  # at least page1 addresses + page2 address

    @pytest.mark.asyncio
    async def test_returns_empty_on_api_failure(self):
        client = AsyncMock()
        client.get = AsyncMock(side_effect=Exception("network error"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        result = await fetch_code_violation_addresses(http_client=client)

        assert result == set()

    @pytest.mark.asyncio
    async def test_returns_empty_on_success_false(self):
        client = AsyncMock()
        client.get = AsyncMock(return_value=_make_ckan_response([], success=False))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        result = await fetch_code_violation_addresses(http_client=client)

        assert result == set()

    @pytest.mark.asyncio
    async def test_skips_records_without_address(self):
        records = [
            {"Case Type": "Dilapidated House or Building", "Street Number": "", "Street Name": "Main"},
            {"Case Type": "Dilapidated House or Building", "Street Number": "100", "Street Name": ""},
            {"Case Type": "Dilapidated House or Building", "Street Number": "200", "Street Name": "Oak"},
        ]
        client = AsyncMock()
        client.get = AsyncMock(return_value=_make_ckan_response(records))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        result = await fetch_code_violation_addresses(http_client=client)

        assert len(result) == 1
        assert any("200" in addr for addr in result)

    @pytest.mark.asyncio
    async def test_deduplicates_same_address(self):
        records = [
            {"Case Type": "Illegal Dumping", "Street Number": "100", "Street Name": "Main", "Street Type": "ST"},
            {"Case Type": "Overgrown Vacant Lot", "Street Number": "100", "Street Name": "Main", "Street Type": "ST"},
        ]
        client = AsyncMock()
        client.get = AsyncMock(return_value=_make_ckan_response(records))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        result = await fetch_code_violation_addresses(http_client=client)

        assert len(result) == 1
