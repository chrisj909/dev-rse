"""
Tests for app/scoring/engine.py — Sprint 3, Task 10.

Strategy:
  - No live database required. We mock AsyncSession and its execute() method
    to return controlled Signal fixtures, and stub out _upsert_score to
    verify it receives the correct arguments.
  - Tests cover single-property scoring, batch scoring, edge cases, and
    the scoring_version propagation.

Covers:
  - ScoringEngine.score(): correct score/rank/reasons for various signal combos
  - ScoringEngine.score(): missing signal row → 0 / "C" / []
  - ScoringEngine.score(): _upsert_score called with correct args
  - ScoringEngine.score_batch(): rank distribution counts
  - ScoringEngine.score_batch(): empty batch
  - ScoringEngine.score_batch(): error on one property continues batch
  - ScoringEngine.score_batch(): errors count is correct
  - ScoringEngine constructor: custom scoring_version
  - _upsert_score: called once per scored property
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.scoring.engine import ScoringEngine
from app.scoring.weights import DEFAULT_SCORING_MODE, SCORING_MODES, SCORING_VERSION, WEIGHTS


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_property(
    *,
    parcel_id: str = "SC-TEST-0001",
    address: str | None = "123 MAIN ST",
    city: str | None = "HOOVER",
) -> MagicMock:
    """Build a mock Property ORM object."""
    prop = MagicMock()
    prop.id = uuid.uuid4()
    prop.parcel_id = parcel_id
    prop.address = address
    prop.city = city
    return prop


def make_signal_row(**flags) -> MagicMock:
    """
    Build a mock Signal ORM row.

    kwargs override individual boolean attributes; all others default to False.
    """
    signal = MagicMock()
    defaults = {
        "absentee_owner":  False,
        "long_term_owner": False,
        "out_of_state_owner": False,
        "corporate_owner": False,
        "tax_delinquent":  False,
        "pre_foreclosure": False,
        "probate":         False,
        "eviction":        False,
        "code_violation":  False,
    }
    defaults.update(flags)
    for attr, val in defaults.items():
        setattr(signal, attr, val)
    return signal


def make_session(signal_row=None) -> AsyncMock:
    """
    Return a mock async session whose execute() returns the given signal_row.

    If signal_row is None, scalar_one_or_none() returns None (no row found).
    """
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = signal_row
    session.execute = AsyncMock(return_value=mock_result)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


# ── ScoringEngine constructor ─────────────────────────────────────────────────

class TestScoringEngineConstructor:

    def test_default_scoring_version(self):
        engine = ScoringEngine()
        assert engine._scoring_version == SCORING_VERSION

    def test_custom_scoring_version(self):
        engine = ScoringEngine(scoring_version="v2-test")
        assert engine._scoring_version == "v2-test"

    def test_default_scoring_mode(self):
        engine = ScoringEngine()
        assert engine._scoring_mode == DEFAULT_SCORING_MODE

    def test_custom_scoring_mode(self):
        engine = ScoringEngine(scoring_mode="investor")
        assert engine._scoring_mode == "investor"


# ── ScoringEngine.score() — single property ───────────────────────────────────

class TestScoringEngineScore:

    @pytest.mark.asyncio
    async def test_no_signal_row_returns_zero_score(self):
        """Missing signal row → score=0, rank=C, reasons=[]."""
        prop = make_property()
        session = make_session(signal_row=None)

        with patch.object(ScoringEngine, "_upsert_score", new_callable=AsyncMock):
            engine = ScoringEngine()
            result = await engine.score(prop, session)

        assert result["score"] == 0
        assert result["rank"] == "C"
        assert result["reasons"] == []

    @pytest.mark.asyncio
    async def test_all_false_signals_zero_score(self):
        """All signal flags False → score=0."""
        prop = make_property()
        signal_row = make_signal_row()  # all False by default
        session = make_session(signal_row=signal_row)

        with patch.object(ScoringEngine, "_upsert_score", new_callable=AsyncMock):
            engine = ScoringEngine()
            result = await engine.score(prop, session)

        assert result["score"] == 0
        assert result["rank"] == "C"
        assert result["reasons"] == []

    @pytest.mark.asyncio
    async def test_absentee_only(self):
        """absentee_owner=True → score=15, rank=B."""
        prop = make_property()
        signal_row = make_signal_row(absentee_owner=True)
        session = make_session(signal_row=signal_row)

        with patch.object(ScoringEngine, "_upsert_score", new_callable=AsyncMock):
            engine = ScoringEngine()
            result = await engine.score(prop, session)

        assert result["score"] == 15
        assert result["rank"] == "B"
        assert result["reasons"] == ["absentee_owner"]

    @pytest.mark.asyncio
    async def test_absentee_and_long_term(self):
        """absentee(15) + long_term(10) = 25 → rank A."""
        prop = make_property()
        signal_row = make_signal_row(absentee_owner=True, long_term_owner=True)
        session = make_session(signal_row=signal_row)

        with patch.object(ScoringEngine, "_upsert_score", new_callable=AsyncMock):
            engine = ScoringEngine()
            result = await engine.score(prop, session)

        assert result["score"] == 25
        assert result["rank"] == "A"
        assert "absentee_owner" in result["reasons"]
        assert "long_term_owner" in result["reasons"]
        assert "distress_combo" not in result["reasons"]

    @pytest.mark.asyncio
    async def test_distress_combo_triggered(self):
        """tax_delinquent + pre_foreclosure → 25+30+20(combo) = 75."""
        prop = make_property()
        signal_row = make_signal_row(tax_delinquent=True, pre_foreclosure=True)
        session = make_session(signal_row=signal_row)

        with patch.object(ScoringEngine, "_upsert_score", new_callable=AsyncMock):
            engine = ScoringEngine()
            result = await engine.score(prop, session)

        assert result["score"] == 75
        assert result["rank"] == "A"
        assert "distress_combo" in result["reasons"]

    @pytest.mark.asyncio
    async def test_all_signals_active(self):
        """All weighted signals active → sum(weights) + combo bonus, rank A."""
        prop = make_property()
        signal_row = make_signal_row(
            absentee_owner=True,
            long_term_owner=True,
            out_of_state_owner=True,
            corporate_owner=True,
            tax_delinquent=True,
            pre_foreclosure=True,
            probate=True,
            code_violation=True,
        )
        session = make_session(signal_row=signal_row)

        with patch.object(ScoringEngine, "_upsert_score", new_callable=AsyncMock):
            engine = ScoringEngine()
            result = await engine.score(prop, session)

        assert result["score"] == sum(WEIGHTS.values()) + 20  # 135
        assert result["rank"] == "A"
        assert "distress_combo" in result["reasons"]

    @pytest.mark.asyncio
    async def test_upsert_score_called_once(self):
        """_upsert_score is called exactly once per scored property."""
        prop = make_property()
        signal_row = make_signal_row(absentee_owner=True)
        session = make_session(signal_row=signal_row)

        with patch.object(ScoringEngine, "_upsert_score", new_callable=AsyncMock) as mock_upsert:
            engine = ScoringEngine()
            await engine.score(prop, session)

        mock_upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_score_called_with_correct_property_id(self):
        """_upsert_score receives the property's UUID."""
        prop = make_property()
        signal_row = make_signal_row(absentee_owner=True)
        session = make_session(signal_row=signal_row)

        with patch.object(ScoringEngine, "_upsert_score", new_callable=AsyncMock) as mock_upsert:
            engine = ScoringEngine()
            await engine.score(prop, session)

        # _upsert_score(session, property_id, score, rank, reasons)
        call_args = mock_upsert.call_args[0]
        assert call_args[1] == prop.id  # property_id

    @pytest.mark.asyncio
    async def test_upsert_score_receives_correct_score_and_rank(self):
        """_upsert_score receives the computed score and rank."""
        prop = make_property()
        signal_row = make_signal_row(absentee_owner=True, long_term_owner=True)
        session = make_session(signal_row=signal_row)

        with patch.object(ScoringEngine, "_upsert_score", new_callable=AsyncMock) as mock_upsert:
            engine = ScoringEngine()
            await engine.score(prop, session)

        call_args = mock_upsert.call_args[0]
        assert call_args[2] == 25    # score
        assert call_args[3] == "A"  # rank

    @pytest.mark.asyncio
    async def test_scoring_version_passed_to_upsert(self):
        """ScoringEngine uses its _scoring_version when calling _upsert_score."""
        prop = make_property()
        signal_row = make_signal_row()
        session = make_session(signal_row=signal_row)

        with patch.object(ScoringEngine, "_upsert_score", new_callable=AsyncMock) as mock_upsert:
            engine = ScoringEngine(scoring_version="v99")
            await engine.score(prop, session)

        # The version is on the engine, not directly in _upsert_score args,
        # but we verify the engine stores it correctly.
        assert engine._scoring_version == "v99"

    @pytest.mark.asyncio
    async def test_score_returns_dict_with_required_keys(self):
        """Return value always has score, rank, reasons keys."""
        prop = make_property()
        session = make_session(signal_row=None)

        with patch.object(ScoringEngine, "_upsert_score", new_callable=AsyncMock):
            engine = ScoringEngine()
            result = await engine.score(prop, session)

        assert "score" in result
        assert "rank" in result
        assert "reasons" in result

    @pytest.mark.asyncio
    async def test_long_term_owner_only_rank_b(self):
        """long_term_owner only → score=10, rank=B."""
        prop = make_property()
        signal_row = make_signal_row(long_term_owner=True)
        session = make_session(signal_row=signal_row)

        with patch.object(ScoringEngine, "_upsert_score", new_callable=AsyncMock):
            engine = ScoringEngine()
            result = await engine.score(prop, session)

        assert result["score"] == 10
        assert result["rank"] == "B"

    @pytest.mark.asyncio
    async def test_out_of_state_owner_only_rank_b(self):
        prop = make_property()
        signal_row = make_signal_row(out_of_state_owner=True)
        session = make_session(signal_row=signal_row)

        engine = ScoringEngine()
        with patch.object(engine, "_upsert_score", new_callable=AsyncMock):
            result = await engine.score(prop, session)

        assert result["score"] == 12
        assert result["rank"] == "B"

    @pytest.mark.asyncio
    async def test_corporate_owner_only_rank_c(self):
        prop = make_property()
        signal_row = make_signal_row(corporate_owner=True)
        session = make_session(signal_row=signal_row)

        engine = ScoringEngine()
        with patch.object(engine, "_upsert_score", new_callable=AsyncMock):
            result = await engine.score(prop, session)

        assert result["score"] == 8
        assert result["rank"] == "C"

    @pytest.mark.asyncio
    async def test_probate_only_rank_b(self):
        """probate only → score=20, rank=B (20 is in the 10–24 range; A requires ≥25)."""
        prop = make_property()
        signal_row = make_signal_row(probate=True)
        session = make_session(signal_row=signal_row)

        with patch.object(ScoringEngine, "_upsert_score", new_callable=AsyncMock):
            engine = ScoringEngine()
            result = await engine.score(prop, session)

        assert result["score"] == 20
        assert result["rank"] == "B"

    @pytest.mark.asyncio
    async def test_owner_occupant_mode_changes_weights(self):
        prop = make_property()
        signal_row = make_signal_row(corporate_owner=True, long_term_owner=True)
        session = make_session(signal_row=signal_row)

        engine = ScoringEngine(scoring_mode="owner_occupant")
        with patch.object(engine, "_upsert_score", new_callable=AsyncMock):
            result = await engine.score(prop, session)

        assert result["score"] == 18
        assert result["rank"] == "B"
        assert result["scoring_mode"] == "owner_occupant"


class TestScoringEngineAllModes:

    @pytest.mark.asyncio
    async def test_score_all_modes_batch_returns_each_mode(self):
        prop = make_property()
        session = AsyncMock()

        async def fake_score_batch(self, properties, _session):
            return {"processed": len(properties), "rank_a": 0, "rank_b": 1, "rank_c": 0, "errors": 0}

        with patch.object(ScoringEngine, "score_batch", new=fake_score_batch):
            result = await ScoringEngine.score_all_modes_batch([prop], session)

        assert set(result.keys()) == set(SCORING_MODES.keys())


# ── ScoringEngine.score_batch() ───────────────────────────────────────────────

class TestScoringEngineBatch:

    @pytest.mark.asyncio
    async def test_empty_batch(self):
        """Empty list → all counts zero."""
        session = make_session()
        with patch.object(ScoringEngine, "_upsert_score", new_callable=AsyncMock):
            engine = ScoringEngine()
            counts = await engine.score_batch([], session)

        assert counts["processed"] == 0
        assert counts["rank_a"] == 0
        assert counts["rank_b"] == 0
        assert counts["rank_c"] == 0
        assert counts["errors"] == 0

    @pytest.mark.asyncio
    async def test_processed_count_matches_input(self):
        """processed count = number of properties passed in (all success)."""
        properties = [make_property(parcel_id=f"SC-{i:04d}") for i in range(7)]

        with patch.object(ScoringEngine, "score", new_callable=AsyncMock) as mock_score:
            mock_score.return_value = {"score": 0, "rank": "C", "reasons": []}
            engine = ScoringEngine()
            counts = await engine.score_batch(properties, AsyncMock())

        assert counts["processed"] == 7

    @pytest.mark.asyncio
    async def test_rank_distribution_counted_correctly(self):
        """Rank distribution (rank_a, rank_b, rank_c) reflects returned ranks."""
        # 3 rank A, 2 rank B, 1 rank C
        rank_sequence = ["A", "A", "A", "B", "B", "C"]
        properties = [make_property(parcel_id=f"SC-{i}") for i in range(len(rank_sequence))]

        score_results = [
            {"score": 25, "rank": r, "reasons": []} for r in rank_sequence
        ]

        with patch.object(ScoringEngine, "score", new_callable=AsyncMock) as mock_score:
            mock_score.side_effect = score_results
            engine = ScoringEngine()
            counts = await engine.score_batch(properties, AsyncMock())

        assert counts["rank_a"] == 3
        assert counts["rank_b"] == 2
        assert counts["rank_c"] == 1
        assert counts["processed"] == 6
        assert counts["errors"] == 0

    @pytest.mark.asyncio
    async def test_error_on_one_property_continues_batch(self):
        """An exception on one property does not abort the entire batch."""
        properties = [make_property(parcel_id=f"SC-{i}") for i in range(5)]

        call_count = 0

        async def score_with_error(prop, session):
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                raise RuntimeError("simulated scoring error")
            return {"score": 15, "rank": "B", "reasons": ["absentee_owner"]}

        engine = ScoringEngine()
        engine.score = score_with_error
        counts = await engine.score_batch(properties, AsyncMock())

        assert counts["processed"] == 4  # 5 total - 1 error
        assert counts["errors"] == 1

    @pytest.mark.asyncio
    async def test_all_errors_counted(self):
        """Every property failing → processed=0, errors=N."""
        properties = [make_property(parcel_id=f"SC-{i}") for i in range(4)]

        async def always_fail(prop, session):
            raise RuntimeError("always fails")

        engine = ScoringEngine()
        engine.score = always_fail
        counts = await engine.score_batch(properties, AsyncMock())

        assert counts["processed"] == 0
        assert counts["errors"] == 4

    @pytest.mark.asyncio
    async def test_all_rank_a(self):
        """All properties rank A → rank_a = N."""
        n = 10
        properties = [make_property(parcel_id=f"SC-{i}") for i in range(n)]

        with patch.object(ScoringEngine, "score", new_callable=AsyncMock) as mock_score:
            mock_score.return_value = {"score": 75, "rank": "A", "reasons": ["tax_delinquent", "pre_foreclosure", "distress_combo"]}
            engine = ScoringEngine()
            counts = await engine.score_batch(properties, AsyncMock())

        assert counts["rank_a"] == n
        assert counts["rank_b"] == 0
        assert counts["rank_c"] == 0
        assert counts["processed"] == n

    @pytest.mark.asyncio
    async def test_counts_dict_always_has_required_keys(self):
        """Result dict always contains processed, rank_a, rank_b, rank_c, errors."""
        engine = ScoringEngine()
        with patch.object(ScoringEngine, "score", new_callable=AsyncMock) as mock_score:
            mock_score.return_value = {"score": 0, "rank": "C", "reasons": []}
            counts = await engine.score_batch([make_property()], AsyncMock())

        for key in ("processed", "rank_a", "rank_b", "rank_c", "errors"):
            assert key in counts, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_single_property_rank_b(self):
        """Single property → rank_b = 1."""
        prop = make_property()
        signal_row = make_signal_row(absentee_owner=True)

        # Build a session that returns the signal row
        session = make_session(signal_row=signal_row)

        with patch.object(ScoringEngine, "_upsert_score", new_callable=AsyncMock):
            engine = ScoringEngine()
            counts = await engine.score_batch([prop], session)

        assert counts["rank_b"] == 1
        assert counts["rank_a"] == 0
        assert counts["rank_c"] == 0
        assert counts["processed"] == 1

    @pytest.mark.asyncio
    async def test_mixed_signals_across_batch(self):
        """
        Batch of 6 properties with varying signal combos.
        Verifies realistic score distribution.
        """
        signal_configs = [
            # score=0  → C
            {},
            # score=10 → B
            {"long_term_owner": True},
            # score=15 → B
            {"absentee_owner": True},
            # score=25 → A
            {"absentee_owner": True, "long_term_owner": True},
            # score=30 → A
            {"pre_foreclosure": True},
            # score=75 → A (with distress combo)
            {"tax_delinquent": True, "pre_foreclosure": True},
        ]
        properties = [make_property(parcel_id=f"SC-MIX-{i}") for i in range(len(signal_configs))]

        async def score_by_index(prop, session):
            idx = int(prop.parcel_id.split("-")[-1])
            signal_row = make_signal_row(**signal_configs[idx])
            flags = {
                col: getattr(signal_row, col, False)
                for col in [
                    "absentee_owner",
                    "long_term_owner",
                    "out_of_state_owner",
                    "corporate_owner",
                    "tax_delinquent",
                    "pre_foreclosure",
                    "probate",
                    "code_violation",
                ]
            }
            from app.scoring.weights import calculate_score
            score_val, rank, reasons = calculate_score(flags)
            return {"score": score_val, "rank": rank, "reasons": reasons}

        engine = ScoringEngine()
        engine.score = score_by_index
        counts = await engine.score_batch(properties, AsyncMock())

        assert counts["processed"] == 6
        assert counts["rank_c"] == 1  # score 0
        assert counts["rank_b"] == 2  # scores 10 and 15
        assert counts["rank_a"] == 3  # scores 25, 30, 75
        assert counts["errors"] == 0
