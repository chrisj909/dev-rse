"""
Tests for app/services/tax_delinquency.py — Sprint 7, Task 14.

Strategy:
  - All DB calls are mocked via AsyncMock so tests run without Postgres.
  - session.execute side_effect is configured per-test to simulate:
      * property found (scalar returns UUID)
      * property not found (scalar returns None)
      * upsert write path
  - We test both ingest_tax_delinquency() and ingest_batch().

Covers:
  - Happy path: delinquent=True written for existing property
  - Happy path: delinquent=False written for existing property (idempotent)
  - Property not found: returns False, no signal written
  - Invalid property_id type: raises ValueError
  - ingest_batch: summary counts, not_found, mixed results
  - _upsert_tax_delinquent: called with correct args
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.services.tax_delinquency import TaxDelinquencyService


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_session(scalar_result=None):
    """
    Return a mock async session.

    scalar_result: value returned by result.scalar_one_or_none()
    """
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scalar_result
    session.execute = AsyncMock(return_value=mock_result)
    return session


def _property_id() -> uuid.UUID:
    return uuid.uuid4()


# ── ingest_tax_delinquency ────────────────────────────────────────────────────

class TestIngestTaxDelinquency:
    """Unit tests for TaxDelinquencyService.ingest_tax_delinquency()."""

    @pytest.mark.asyncio
    async def test_returns_true_when_property_found(self):
        """Returns True when the property exists and the write succeeds."""
        pid = _property_id()
        session = _make_session(scalar_result=pid)

        service = TaxDelinquencyService()
        result = await service.ingest_tax_delinquency(pid, is_delinquent=True, session=session)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_property_not_found(self):
        """Returns False when the property UUID is not in the DB."""
        pid = _property_id()
        session = _make_session(scalar_result=None)

        service = TaxDelinquencyService()
        result = await service.ingest_tax_delinquency(pid, is_delinquent=True, session=session)

        assert result is False

    @pytest.mark.asyncio
    async def test_execute_called_at_least_once_on_success(self):
        """session.execute is called at least once (property lookup + upsert)."""
        pid = _property_id()
        session = _make_session(scalar_result=pid)

        service = TaxDelinquencyService()
        await service.ingest_tax_delinquency(pid, is_delinquent=True, session=session)

        assert session.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_execute_called_only_for_lookup_when_not_found(self):
        """When property is not found, only the lookup execute happens (no upsert)."""
        pid = _property_id()
        session = _make_session(scalar_result=None)

        service = TaxDelinquencyService()
        await service.ingest_tax_delinquency(pid, is_delinquent=False, session=session)

        # Only the SELECT should have been called (1 execute call for the lookup)
        assert session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_delinquent_false_still_writes(self):
        """is_delinquent=False is a valid write — clearing a flag."""
        pid = _property_id()
        session = _make_session(scalar_result=pid)

        service = TaxDelinquencyService()
        result = await service.ingest_tax_delinquency(pid, is_delinquent=False, session=session)

        assert result is True

    @pytest.mark.asyncio
    async def test_raises_for_non_uuid_property_id(self):
        """Passing a string instead of UUID raises ValueError."""
        session = _make_session()

        service = TaxDelinquencyService()
        with pytest.raises(ValueError, match="property_id must be a UUID"):
            await service.ingest_tax_delinquency(
                property_id="not-a-uuid",  # type: ignore[arg-type]
                is_delinquent=True,
                session=session,
            )

    @pytest.mark.asyncio
    async def test_raises_for_int_property_id(self):
        """Passing an int instead of UUID raises ValueError."""
        session = _make_session()

        service = TaxDelinquencyService()
        with pytest.raises(ValueError):
            await service.ingest_tax_delinquency(
                property_id=12345,  # type: ignore[arg-type]
                is_delinquent=True,
                session=session,
            )

    @pytest.mark.asyncio
    async def test_upsert_helper_called_on_found_property(self):
        """_upsert_tax_delinquent is called when property exists."""
        pid = _property_id()
        session = _make_session(scalar_result=pid)

        service = TaxDelinquencyService()
        with patch.object(
            TaxDelinquencyService,
            "_upsert_tax_delinquent",
            new_callable=AsyncMock,
        ) as mock_upsert:
            await service.ingest_tax_delinquency(pid, is_delinquent=True, session=session)

        mock_upsert.assert_called_once_with(session, pid, True)

    @pytest.mark.asyncio
    async def test_upsert_helper_not_called_when_not_found(self):
        """_upsert_tax_delinquent is NOT called when property is missing."""
        pid = _property_id()
        session = _make_session(scalar_result=None)

        service = TaxDelinquencyService()
        with patch.object(
            TaxDelinquencyService,
            "_upsert_tax_delinquent",
            new_callable=AsyncMock,
        ) as mock_upsert:
            await service.ingest_tax_delinquency(pid, is_delinquent=True, session=session)

        mock_upsert.assert_not_called()


# ── ingest_batch ──────────────────────────────────────────────────────────────

class TestIngestBatch:
    """Unit tests for TaxDelinquencyService.ingest_batch()."""

    @pytest.mark.asyncio
    async def test_empty_batch_returns_zeros(self):
        """Empty input → all counts zero."""
        session = _make_session()
        service = TaxDelinquencyService()
        counts = await service.ingest_batch([], session=session)

        assert counts == {"processed": 0, "updated": 0, "not_found": 0}

    @pytest.mark.asyncio
    async def test_all_found_all_updated(self):
        """All properties found → all updated."""
        pids = [_property_id() for _ in range(3)]
        records = [{"property_id": pid, "is_delinquent": True} for pid in pids]
        session = _make_session()
        service = TaxDelinquencyService()

        with patch.object(
            service,
            "ingest_tax_delinquency",
            new_callable=AsyncMock,
            return_value=True,
        ):
            counts = await service.ingest_batch(records, session=session)

        assert counts["processed"] == 3
        assert counts["updated"] == 3
        assert counts["not_found"] == 0

    @pytest.mark.asyncio
    async def test_none_found_all_not_found(self):
        """No properties found → all not_found."""
        pids = [_property_id() for _ in range(2)]
        records = [{"property_id": pid, "is_delinquent": False} for pid in pids]
        session = _make_session()
        service = TaxDelinquencyService()

        with patch.object(
            service,
            "ingest_tax_delinquency",
            new_callable=AsyncMock,
            return_value=False,
        ):
            counts = await service.ingest_batch(records, session=session)

        assert counts["processed"] == 2
        assert counts["updated"] == 0
        assert counts["not_found"] == 2

    @pytest.mark.asyncio
    async def test_mixed_found_and_not_found(self):
        """Mix of found and not-found → counts split correctly."""
        pid_found = _property_id()
        pid_missing = _property_id()
        records = [
            {"property_id": pid_found, "is_delinquent": True},
            {"property_id": pid_missing, "is_delinquent": True},
        ]
        session = _make_session()
        service = TaxDelinquencyService()

        async def side_effect(property_id, is_delinquent, session):
            return property_id == pid_found

        with patch.object(service, "ingest_tax_delinquency", side_effect=side_effect):
            counts = await service.ingest_batch(records, session=session)

        assert counts["processed"] == 2
        assert counts["updated"] == 1
        assert counts["not_found"] == 1

    @pytest.mark.asyncio
    async def test_records_missing_property_id_are_skipped(self):
        """Records without property_id key are skipped without error."""
        records = [
            {"is_delinquent": True},  # no property_id
            {"property_id": _property_id(), "is_delinquent": False},
        ]
        session = _make_session()
        service = TaxDelinquencyService()

        with patch.object(
            service,
            "ingest_tax_delinquency",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_ingest:
            counts = await service.ingest_batch(records, session=session)

        # Only the valid record should have triggered ingest_tax_delinquency
        assert mock_ingest.call_count == 1
        assert counts["processed"] == 1

    @pytest.mark.asyncio
    async def test_is_delinquent_defaults_to_false_when_missing(self):
        """If is_delinquent key is absent, it defaults to False."""
        pid = _property_id()
        records = [{"property_id": pid}]  # no is_delinquent
        session = _make_session()
        service = TaxDelinquencyService()

        captured = []

        async def capture(property_id, is_delinquent, session):
            captured.append(is_delinquent)
            return True

        with patch.object(service, "ingest_tax_delinquency", side_effect=capture):
            await service.ingest_batch(records, session=session)

        assert captured == [False]

    @pytest.mark.asyncio
    async def test_bool_coercion_truthy_values(self):
        """Truthy values in is_delinquent are coerced to True."""
        pid = _property_id()
        records = [{"property_id": pid, "is_delinquent": 1}]
        session = _make_session()
        service = TaxDelinquencyService()

        captured = []

        async def capture(property_id, is_delinquent, session):
            captured.append(is_delinquent)
            return True

        with patch.object(service, "ingest_tax_delinquency", side_effect=capture):
            await service.ingest_batch(records, session=session)

        assert captured[0] is True


# ── TaxDelinquencyService instantiation ──────────────────────────────────────

class TestServiceInstantiation:
    """Sanity checks on the service class itself."""

    def test_service_is_instantiable(self):
        """TaxDelinquencyService can be created with no arguments."""
        service = TaxDelinquencyService()
        assert service is not None

    def test_service_has_ingest_method(self):
        """ingest_tax_delinquency method exists."""
        service = TaxDelinquencyService()
        assert callable(service.ingest_tax_delinquency)

    def test_service_has_batch_method(self):
        """ingest_batch method exists."""
        service = TaxDelinquencyService()
        assert callable(service.ingest_batch)
