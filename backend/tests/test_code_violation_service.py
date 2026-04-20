"""
Tests for app/services/code_violation_service.py

Strategy:
  - Mock the AsyncSession so no real DB is needed.
  - Verify address matching, flag values, bulk upsert call, and counts.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.code_violation_service import CodeViolationService


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


def _make_prop(address: str | None = "100 MAIN ST", city: str = "Birmingham") -> MagicMock:
    prop = MagicMock()
    prop.id = uuid.uuid4()
    prop.address = address
    prop.city = city
    return prop


# ── ingest_batch ──────────────────────────────────────────────────────────────

class TestIngestBatch:
    @pytest.mark.asyncio
    async def test_empty_properties_returns_zeros(self):
        svc = CodeViolationService()
        result = await svc.ingest_batch([], _make_session(), {"100 MAIN ST"})
        assert result == {"processed": 0, "flagged": 0}

    @pytest.mark.asyncio
    async def test_empty_violation_set_flags_nothing(self):
        svc = CodeViolationService()
        props = [_make_prop("100 MAIN ST"), _make_prop("200 OAK AVE")]
        session = _make_session()
        result = await svc.ingest_batch(props, session, set())
        assert result["processed"] == 2
        assert result["flagged"] == 0

    @pytest.mark.asyncio
    async def test_matching_address_is_flagged(self):
        from app.services.address_normalizer import normalize_address

        raw = "100 Main Street"
        normalized = normalize_address(raw)

        svc = CodeViolationService()
        props = [_make_prop(raw)]
        session = _make_session()
        result = await svc.ingest_batch(props, session, {normalized})

        assert result["processed"] == 1
        assert result["flagged"] == 1

    @pytest.mark.asyncio
    async def test_non_matching_address_not_flagged(self):
        svc = CodeViolationService()
        props = [_make_prop("999 NOWHERE LN")]
        session = _make_session()
        result = await svc.ingest_batch(props, session, {"100 MAIN ST"})
        assert result["flagged"] == 0

    @pytest.mark.asyncio
    async def test_property_without_address_counted_but_not_flagged(self):
        svc = CodeViolationService()
        props = [_make_prop(address=None)]
        session = _make_session()
        result = await svc.ingest_batch(props, session, {"100 MAIN ST"})
        assert result["processed"] == 1
        assert result["flagged"] == 0

    @pytest.mark.asyncio
    async def test_bulk_upsert_called_once(self):
        from app.services.address_normalizer import normalize_address

        normalized = normalize_address("100 Main St")
        svc = CodeViolationService()
        props = [_make_prop("100 Main St"), _make_prop("200 Oak Ave")]
        session = _make_session()
        await svc.ingest_batch(props, session, {normalized})

        # execute called once for the bulk upsert
        assert session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_mixed_batch_counts_correctly(self):
        from app.services.address_normalizer import normalize_address

        addr1 = normalize_address("100 Main St")
        addr2 = normalize_address("200 Oak Ave")

        svc = CodeViolationService()
        props = [
            _make_prop("100 Main St"),
            _make_prop("200 Oak Ave"),
            _make_prop("300 Elm Dr"),     # no violation
            _make_prop(address=None),     # no address
        ]
        session = _make_session()
        result = await svc.ingest_batch(props, session, {addr1, addr2})

        assert result["processed"] == 4
        assert result["flagged"] == 2

    @pytest.mark.asyncio
    async def test_no_execute_when_all_props_missing_address(self):
        svc = CodeViolationService()
        props = [_make_prop(address=None), _make_prop(address=None)]
        session = _make_session()
        await svc.ingest_batch(props, session, {"100 MAIN ST"})
        # No values to upsert → execute should not be called
        session.execute.assert_not_called()
