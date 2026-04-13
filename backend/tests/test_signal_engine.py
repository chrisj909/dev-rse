"""
Tests for app/signals/engine.py — Sprint 3 (Task 7), updated Sprint 7 (Task 15).

Strategy:
  - Pure-logic tests run without a database by using an in-memory SQLite
    engine (via the async SQLAlchemy dialect) or by mocking the DB calls.
  - We focus on the signal detection logic and the adapter functions,
    since the DB upsert path is already covered by test_ingestion_pipeline.py.
  - We use unittest.mock to stub out the async session so tests run fast
    and without a running Postgres instance.

Covers:
  - _absentee_owner_detector adapter
  - _long_term_owner_detector adapter
  - SignalEngine.process — correct flags produced for various property states
  - SignalEngine.process_batch — aggregated counts correct
  - SignalEngine constructor (custom signal registry)
  - Error handling: detector raises an exception → flag defaults to False
  - Class-level registry (Sprint 7)
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.signals.engine import (
    SignalEngine,
    _absentee_owner_detector,
    _corporate_owner_detector,
    _long_term_owner_detector,
    _out_of_state_owner_detector,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_property(
    *,
    parcel_id: str = "SC-TEST-0001",
    address: str | None = "123 MAIN ST",
    city: str | None = "HOOVER",
    state: str = "AL",
    zip_code: str | None = "35244",
    mailing_address: str | None = None,
    last_sale_date: date | None = None,
) -> MagicMock:
    """
    Build a mock Property ORM object for use in tests.
    The mock satisfies all attribute accesses made by the engine and adapters.
    """
    prop = MagicMock()
    prop.id = uuid.uuid4()
    prop.parcel_id = parcel_id
    prop.address = address
    prop.city = city
    prop.state = state
    prop.zip = zip_code
    prop.mailing_address = mailing_address
    prop.last_sale_date = last_sale_date
    return prop


def make_session() -> AsyncMock:
    """Return a mock async SQLAlchemy session that swallows all writes."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


# ── _absentee_owner_detector ──────────────────────────────────────────────────

class TestAbsenteeOwnerDetectorAdapter:
    """Adapter converts Property ORM → detect_absentee_owner call."""

    def test_owner_at_property_not_absentee(self):
        """Mailing address matches full property address → not absentee."""
        prop = make_property(
            address="123 MAIN ST",
            city="HOOVER",
            state="AL",
            zip_code="35244",
            mailing_address="123 MAIN ST HOOVER AL 35244",
        )
        assert _absentee_owner_detector(prop) is False

    def test_different_mailing_is_absentee(self):
        """Mailing address differs → absentee."""
        prop = make_property(
            address="456 OAK AVE",
            city="ALABASTER",
            state="AL",
            zip_code="35007",
            mailing_address="PO BOX 100 ATLANTA GA 30303",
        )
        assert _absentee_owner_detector(prop) is True

    def test_no_mailing_address_not_absentee(self):
        """Missing mailing address → do not flag (insufficient data)."""
        prop = make_property(mailing_address=None)
        assert _absentee_owner_detector(prop) is False

    def test_no_street_address_not_absentee(self):
        """Missing street address → cannot build full address → not flagged."""
        prop = make_property(address=None, mailing_address="456 OAK AVE ATLANTA GA 30303")
        assert _absentee_owner_detector(prop) is False

    def test_out_of_state_mailing_is_absentee(self):
        """Owner mails to another state → absentee."""
        prop = make_property(
            address="558 POPLAR ST",
            city="ALABASTER",
            state="AL",
            zip_code="35007",
            mailing_address="4509 OAKWOOD DR NASHVILLE TN 37215",
        )
        assert _absentee_owner_detector(prop) is True

    def test_same_city_different_street_is_absentee(self):
        """Same city, different street → absentee (investment property)."""
        prop = make_property(
            address="208 MAGNOLIA DR",
            city="HOOVER",
            state="AL",
            zip_code="35244",
            mailing_address="900 RIDGE RD HOOVER AL 35244",
        )
        assert _absentee_owner_detector(prop) is True

    def test_missing_city_still_works(self):
        """City may be None — address built from what's available."""
        prop = make_property(
            address="123 MAIN ST",
            city=None,
            state="AL",
            zip_code="35244",
            mailing_address="123 MAIN ST AL 35244",
        )
        # Should not raise; returns bool
        result = _absentee_owner_detector(prop)
        assert isinstance(result, bool)

    def test_datetime_mailing_address_type_not_absentee(self):
        """Property with all address components present and matching."""
        prop = make_property(
            address="315 PINE CT",
            city="HOOVER",
            state="AL",
            zip_code="35226",
            mailing_address="315 PINE CT HOOVER AL 35226",
        )
        assert _absentee_owner_detector(prop) is False


# ── _long_term_owner_detector ─────────────────────────────────────────────────

class TestLongTermOwnerDetectorAdapter:
    """Adapter converts Property ORM last_sale_date → detect_long_term_owner."""

    def test_sale_11_years_ago_is_long_term(self):
        """last_sale_date > 10 years → long-term."""
        prop = make_property(last_sale_date=date(2013, 1, 1))
        assert _long_term_owner_detector(prop) is True

    def test_recent_sale_not_long_term(self):
        """recent last_sale_date → not long-term."""
        prop = make_property(last_sale_date=date(2023, 6, 1))
        assert _long_term_owner_detector(prop) is False

    def test_missing_sale_date_not_flagged(self):
        """None last_sale_date → not flagged."""
        prop = make_property(last_sale_date=None)
        assert _long_term_owner_detector(prop) is False

    def test_datetime_object_works(self):
        """ORM may return datetime instead of date — adapter handles it."""
        prop = make_property(last_sale_date=datetime(2010, 5, 15))
        assert _long_term_owner_detector(prop) is True

    def test_sale_in_future_not_long_term(self):
        """Future sale date → not long-term."""
        prop = make_property(last_sale_date=date(2030, 1, 1))
        assert _long_term_owner_detector(prop) is False

    def test_very_old_sale_is_long_term(self):
        """Sale in 1985 → definitely long-term."""
        prop = make_property(last_sale_date=date(1985, 3, 12))
        assert _long_term_owner_detector(prop) is True


class TestCrossCountyOwnerPatternAdapters:
    def test_out_of_state_owner_detector_true(self):
        prop = make_property(mailing_address="PO BOX 99 ATLANTA GA 30303")
        assert _out_of_state_owner_detector(prop) is True

    def test_out_of_state_owner_detector_false(self):
        prop = make_property(mailing_address="PO BOX 99 BIRMINGHAM AL 35203")
        assert _out_of_state_owner_detector(prop) is False

    def test_corporate_owner_detector_true(self):
        prop = make_property()
        prop.owner_name = "MAPLE STREET HOLDINGS LLC"
        assert _corporate_owner_detector(prop) is True

    def test_corporate_owner_detector_false(self):
        prop = make_property()
        prop.owner_name = "JANE DOE"
        assert _corporate_owner_detector(prop) is False


# ── SignalEngine.process ──────────────────────────────────────────────────────

class TestSignalEngineProcess:
    """Single-property processing via SignalEngine.process."""

    @pytest.mark.asyncio
    async def test_returns_correct_flags_both_signals(self):
        """Property that is absentee and long-term → both flags True."""
        prop = make_property(
            address="208 MAGNOLIA DR",
            city="HOOVER",
            state="AL",
            zip_code="35244",
            mailing_address="PO BOX 4421 BIRMINGHAM AL 35203",
            last_sale_date=date(2007, 6, 22),
        )
        session = make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock) as mock_upsert:
            engine = SignalEngine()
            flags = await engine.process(prop, session)

        assert flags["absentee_owner"] is True
        assert flags["long_term_owner"] is True
        assert flags["out_of_state_owner"] is False
        assert flags["corporate_owner"] is False
        mock_upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_correct_flags_no_signals(self):
        """Owner-occupied, recently purchased → both flags False."""
        prop = make_property(
            address="315 PINE CT",
            city="HOOVER",
            state="AL",
            zip_code="35226",
            mailing_address="315 PINE CT HOOVER AL 35226",
            last_sale_date=date(2022, 3, 10),
        )
        session = make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine()
            flags = await engine.process(prop, session)

        assert flags["absentee_owner"] is False
        assert flags["long_term_owner"] is False
        assert flags["out_of_state_owner"] is False
        assert flags["corporate_owner"] is False

    @pytest.mark.asyncio
    async def test_returns_correct_flags_only_absentee(self):
        """Recent purchase, different mailing → absentee only."""
        prop = make_property(
            address="329 HICKORY HILL",
            city="ALABASTER",
            state="AL",
            zip_code="35007",
            mailing_address="888 COMMERCE PKWY STE 300 ATLANTA GA 30339",
            last_sale_date=date(2022, 12, 1),
        )
        session = make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine()
            flags = await engine.process(prop, session)

        assert flags["absentee_owner"] is True
        assert flags["long_term_owner"] is False
        assert flags["out_of_state_owner"] is True
        assert flags["corporate_owner"] is False

    @pytest.mark.asyncio
    async def test_returns_correct_flags_only_long_term(self):
        """Owner-occupied, held > 10 years → long_term only."""
        prop = make_property(
            address="105 CHURCH ST",
            city="ALABASTER",
            state="AL",
            zip_code="35007",
            mailing_address="105 CHURCH ST ALABASTER AL 35007",
            last_sale_date=date(2003, 7, 8),
        )
        session = make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine()
            flags = await engine.process(prop, session)

        assert flags["absentee_owner"] is False
        assert flags["long_term_owner"] is True
        assert flags["out_of_state_owner"] is False
        assert flags["corporate_owner"] is False

    @pytest.mark.asyncio
    async def test_returns_both_keys_always(self):
        """Result dict always contains both registered signal keys."""
        prop = make_property(last_sale_date=None, mailing_address=None)
        session = make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine()
            flags = await engine.process(prop, session)

        assert "absentee_owner" in flags
        assert "long_term_owner" in flags
        assert "out_of_state_owner" in flags
        assert "corporate_owner" in flags

    @pytest.mark.asyncio
    async def test_upsert_called_with_property_id(self):
        """_upsert_signal is called with the property's UUID."""
        prop = make_property()
        session = make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock) as mock_upsert:
            engine = SignalEngine()
            await engine.process(prop, session)

        call_args = mock_upsert.call_args
        # call_args[0] = positional args: (session, property_id, flags)
        assert call_args[0][1] == prop.id

    @pytest.mark.asyncio
    async def test_detector_exception_defaults_to_false(self):
        """If a detector raises an exception, the signal defaults to False (not crash)."""
        def bad_detector(prop):
            raise RuntimeError("detector failed")

        prop = make_property()
        session = make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine(signals=[("absentee_owner", bad_detector)])
            flags = await engine.process(prop, session)

        assert flags["absentee_owner"] is False

    @pytest.mark.asyncio
    async def test_custom_signal_registry(self):
        """Engine respects a custom signal registry passed to the constructor."""
        always_true = lambda prop: True   # noqa: E731
        always_false = lambda prop: False  # noqa: E731

        prop = make_property()
        session = make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine(signals=[
                ("custom_a", always_true),
                ("custom_b", always_false),
            ])
            flags = await engine.process(prop, session)

        assert flags["custom_a"] is True
        assert flags["custom_b"] is False


# ── SignalEngine.process_batch ────────────────────────────────────────────────

class TestSignalEngineProcessBatch:
    """Batch processing via SignalEngine.process_batch."""

    @pytest.mark.asyncio
    async def test_processed_count_matches_input(self):
        """processed count equals the number of properties passed in."""
        properties = [make_property(parcel_id=f"SC-{i:04d}") for i in range(10)]
        session = make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine()
            counts = await engine.process_batch(properties, session)

        assert counts["processed"] == 10

    @pytest.mark.asyncio
    async def test_signal_counts_are_accurate(self):
        """Per-signal counts reflect the number of True detections."""
        # 5 absentee properties, 5 owner-occupied.  None are long-term owners.
        absentee_props = [
            make_property(
                parcel_id=f"SC-ABS-{i}",
                address="208 MAGNOLIA DR",
                city="HOOVER",
                state="AL",
                zip_code="35244",
                mailing_address="PO BOX 1234 ATLANTA GA 30303",
                last_sale_date=date(2023, 1, 1),  # recent → not long-term
            )
            for i in range(5)
        ]
        occupied_props = [
            make_property(
                parcel_id=f"SC-OCC-{i}",
                address="315 PINE CT",
                city="HOOVER",
                state="AL",
                zip_code="35226",
                mailing_address="315 PINE CT HOOVER AL 35226",
                last_sale_date=date(2023, 6, 1),
            )
            for i in range(5)
        ]

        session = make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine()
            counts = await engine.process_batch(absentee_props + occupied_props, session)

        assert counts["processed"] == 10
        assert counts["absentee_owner"] == 5
        assert counts["long_term_owner"] == 0
        assert counts["out_of_state_owner"] == 5
        assert counts["corporate_owner"] == 0

    @pytest.mark.asyncio
    async def test_empty_batch_returns_zeros(self):
        """Empty input list → all counts are zero."""
        session = make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine()
            counts = await engine.process_batch([], session)

        assert counts["processed"] == 0
        assert counts["absentee_owner"] == 0
        assert counts["long_term_owner"] == 0
        assert counts["out_of_state_owner"] == 0
        assert counts["corporate_owner"] == 0

    @pytest.mark.asyncio
    async def test_batch_continues_after_single_error(self):
        """A failure on one property should not abort the entire batch."""
        good_prop = make_property(parcel_id="SC-GOOD-001")
        bad_prop = make_property(parcel_id="SC-BAD-001")

        # Make the engine raise on bad_prop by corrupting its attribute
        bad_prop.id = None  # will cause issues in _upsert_signal

        call_count = 0

        async def mock_upsert(session, property_id, flags):
            nonlocal call_count
            if property_id is None:
                raise RuntimeError("simulated DB error")
            call_count += 1

        with patch.object(SignalEngine, "_upsert_signal", side_effect=mock_upsert):
            engine = SignalEngine()
            counts = await engine.process_batch([bad_prop, good_prop], session=make_session())

        # good_prop should still be processed
        assert counts["processed"] >= 1

    @pytest.mark.asyncio
    async def test_long_term_count_accurate(self):
        """Long-term owner detections are counted correctly."""
        long_term_props = [
            make_property(
                parcel_id=f"SC-LT-{i}",
                mailing_address=None,  # not absentee (missing data)
                last_sale_date=date(2005, 3, 15),  # > 10 years ago
            )
            for i in range(8)
        ]

        session = make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine()
            counts = await engine.process_batch(long_term_props, session)

        assert counts["long_term_owner"] == 8
        assert counts["absentee_owner"] == 0  # mailing None → not flagged
        assert counts["out_of_state_owner"] == 0


# ── Class registry smoke tests ────────────────────────────────────────────────

class TestRegisteredSignals:
    """Smoke tests for the class-level signal registry (Sprint 7 refactor)."""

    def test_registered_signals_not_empty(self):
        """At least one signal must be registered."""
        assert len(SignalEngine.registered_signals()) > 0

    def test_registered_signal_names(self):
        """MVP includes absentee_owner and long_term_owner."""
        names = [name for name, _ in SignalEngine.registered_signals()]
        assert "absentee_owner" in names
        assert "long_term_owner" in names

    def test_each_entry_is_callable(self):
        """Every registered detector must be callable."""
        for name, detector in SignalEngine.registered_signals():
            assert callable(detector), f"Detector for '{name}' is not callable"

    def test_default_engine_uses_class_registry(self):
        """Engine with no args uses the class-level registry (no override)."""
        engine = SignalEngine()
        assert engine._signals_override is None
        # _signals property delegates to class registry
        assert engine._signals == SignalEngine.registered_signals()

    def test_custom_engine_uses_provided_signals(self):
        """Engine with explicit signals list uses that list (override)."""
        custom = [("test_signal", lambda p: True)]
        engine = SignalEngine(signals=custom)
        assert engine._signals is custom
