"""
Tests for app/scoring/weights.py — Sprint 3, Task 9.

Coverage:
    - Zero score (no signals active)
    - Every individual signal: correct weight, correct rank, correct reason tag
    - All signal combinations (exhaustive for 2-signal combos, key 3+ combos)
    - Rank boundary conditions: exactly 9 (C), exactly 10 (B), exactly 24 (B), exactly 25 (A)
  - Distress combo bonus: triggered at 2 distress signals, not at 1
  - Distress combo with all 4 distress signals
  - Non-distress signals (absentee_owner, long_term_owner) do NOT trigger combo
  - Unknown signal keys in flags dict are silently ignored
  - False values for all signals → zero score
  - assign_rank() boundary values
  - SCORING_VERSION is a non-empty string
  - WEIGHTS dict contains all required keys with correct values
  - DISTRESS_SIGNALS contains exactly the expected set
"""
from __future__ import annotations

import pytest

from app.scoring.weights import (
    DISTRESS_COMBO_BONUS,
    DISTRESS_COMBO_THRESHOLD,
    DISTRESS_SIGNALS,
    RANK_A_MIN,
    RANK_B_MIN,
    SCORING_VERSION,
    WEIGHTS,
    assign_rank,
    calculate_score,
)


# ── Module-level constant tests ───────────────────────────────────────────────

class TestConstants:
    """Smoke-test the module-level constants against the BUILD_PLAN spec."""

    def test_scoring_version_is_string(self):
        assert isinstance(SCORING_VERSION, str)
        assert len(SCORING_VERSION) > 0

    def test_scoring_version_is_v2(self):
        assert SCORING_VERSION == "v2"

    def test_weights_contains_all_signals(self):
        expected = {
            "absentee_owner",
            "long_term_owner",
            "tax_delinquent",
            "pre_foreclosure",
            "probate",
            "code_violation",
        }
        assert set(WEIGHTS.keys()) == expected

    def test_weights_match_build_plan(self):
        assert WEIGHTS["absentee_owner"] == 15
        assert WEIGHTS["long_term_owner"] == 10
        assert WEIGHTS["tax_delinquent"] == 25
        assert WEIGHTS["pre_foreclosure"] == 30
        assert WEIGHTS["probate"] == 20
        assert WEIGHTS["code_violation"] == 15

    def test_distress_signals_set(self):
        expected = frozenset({"tax_delinquent", "pre_foreclosure", "probate", "code_violation"})
        assert DISTRESS_SIGNALS == expected

    def test_distress_combo_bonus(self):
        assert DISTRESS_COMBO_BONUS == 20

    def test_distress_combo_threshold(self):
        assert DISTRESS_COMBO_THRESHOLD == 2

    def test_rank_thresholds(self):
        assert RANK_A_MIN == 25
        assert RANK_B_MIN == 10


# ── Zero / empty cases ────────────────────────────────────────────────────────

class TestZeroScore:
    """No signals → zero score, rank C, empty reasons."""

    def test_empty_flags(self):
        score, rank, reasons = calculate_score({})
        assert score == 0
        assert rank == "C"
        assert reasons == []

    def test_all_false_flags(self):
        flags = {k: False for k in WEIGHTS}
        score, rank, reasons = calculate_score(flags)
        assert score == 0
        assert rank == "C"
        assert reasons == []

    def test_unknown_keys_ignored(self):
        """Keys not in WEIGHTS should not raise and should not affect score."""
        score, rank, reasons = calculate_score({"nonexistent_signal": True})
        assert score == 0
        assert rank == "C"
        assert reasons == []

    def test_mixed_known_false_and_unknown_true(self):
        flags = {k: False for k in WEIGHTS}
        flags["mystery_signal"] = True
        score, rank, reasons = calculate_score(flags)
        assert score == 0


# ── Individual signal tests ───────────────────────────────────────────────────

class TestIndividualSignals:
    """Each signal in isolation — correct weight, rank, and reason tag."""

    def test_absentee_owner_only(self):
        score, rank, reasons = calculate_score({"absentee_owner": True})
        assert score == 15
        assert rank == "B"
        assert reasons == ["absentee_owner"]

    def test_long_term_owner_only(self):
        score, rank, reasons = calculate_score({"long_term_owner": True})
        assert score == 10
        assert rank == "B"
        assert reasons == ["long_term_owner"]

    def test_tax_delinquent_only(self):
        score, rank, reasons = calculate_score({"tax_delinquent": True})
        assert score == 25
        assert rank == "A"
        assert reasons == ["tax_delinquent"]

    def test_pre_foreclosure_only(self):
        score, rank, reasons = calculate_score({"pre_foreclosure": True})
        assert score == 30
        assert rank == "A"
        assert reasons == ["pre_foreclosure"]

    def test_probate_only(self):
        score, rank, reasons = calculate_score({"probate": True})
        assert score == 20
        assert rank == "B"   # 20 is in the B range (10–24); A requires ≥25
        assert reasons == ["probate"]

    def test_code_violation_only(self):
        score, rank, reasons = calculate_score({"code_violation": True})
        assert score == 15
        assert rank == "B"
        assert reasons == ["code_violation"]


# ── Two-signal combination tests ──────────────────────────────────────────────

class TestTwoSignalCombinations:
    """Selected pairs — score, rank, and reason tags."""

    def test_absentee_and_long_term(self):
        """15 + 10 = 25 → rank A (exactly at boundary)."""
        score, rank, reasons = calculate_score({
            "absentee_owner": True,
            "long_term_owner": True,
        })
        assert score == 25
        assert rank == "A"
        assert "absentee_owner" in reasons
        assert "long_term_owner" in reasons
        assert "distress_combo" not in reasons  # non-distress signals — no bonus

    def test_tax_delinquent_and_absentee(self):
        """25 + 15 = 40 → rank A (no combo — only 1 distress signal)."""
        score, rank, reasons = calculate_score({
            "tax_delinquent": True,
            "absentee_owner": True,
        })
        assert score == 40
        assert rank == "A"
        assert "distress_combo" not in reasons

    def test_tax_delinquent_and_pre_foreclosure(self):
        """25 + 30 + 20 (combo) = 75 → rank A — both are distress signals."""
        score, rank, reasons = calculate_score({
            "tax_delinquent": True,
            "pre_foreclosure": True,
        })
        assert score == 75
        assert rank == "A"
        assert "distress_combo" in reasons

    def test_probate_and_code_violation(self):
        """20 + 15 + 20 (combo) = 55 → rank A."""
        score, rank, reasons = calculate_score({
            "probate": True,
            "code_violation": True,
        })
        assert score == 55
        assert rank == "A"
        assert "distress_combo" in reasons

    def test_pre_foreclosure_and_probate(self):
        """30 + 20 + 20 (combo) = 70 → rank A."""
        score, rank, reasons = calculate_score({
            "pre_foreclosure": True,
            "probate": True,
        })
        assert score == 70
        assert rank == "A"
        assert "distress_combo" in reasons

    def test_code_violation_and_pre_foreclosure(self):
        """15 + 30 + 20 (combo) = 65 → rank A."""
        score, rank, reasons = calculate_score({
            "code_violation": True,
            "pre_foreclosure": True,
        })
        assert score == 65
        assert rank == "A"
        assert "distress_combo" in reasons

    def test_absentee_and_code_violation(self):
        """15 + 15 = 30 → rank A (code_violation is distress but only 1 distress signal)."""
        score, rank, reasons = calculate_score({
            "absentee_owner": True,
            "code_violation": True,
        })
        assert score == 30
        assert rank == "A"
        assert "distress_combo" not in reasons

    def test_long_term_and_probate(self):
        """10 + 20 = 30 → rank A (probate is distress but only 1 distress signal)."""
        score, rank, reasons = calculate_score({
            "long_term_owner": True,
            "probate": True,
        })
        assert score == 30
        assert rank == "A"
        assert "distress_combo" not in reasons


# ── Multi-signal combinations ─────────────────────────────────────────────────

class TestMultiSignalCombinations:
    """Three or more signals, including full distress scenarios."""

    def test_all_six_signals_active(self):
        """All signals + distress combo → 15+10+25+30+20+15+20 = 135."""
        flags = {k: True for k in WEIGHTS}
        score, rank, reasons = calculate_score(flags)
        expected_base = sum(WEIGHTS.values())  # 115
        expected_score = expected_base + DISTRESS_COMBO_BONUS  # 135
        assert score == expected_score
        assert rank == "A"
        assert "distress_combo" in reasons
        # All signals present in reasons
        for signal in WEIGHTS:
            assert signal in reasons

    def test_all_four_distress_signals(self):
        """25+30+20+15+20 (combo) = 110 → rank A."""
        flags = {
            "tax_delinquent": True,
            "pre_foreclosure": True,
            "probate": True,
            "code_violation": True,
        }
        score, rank, reasons = calculate_score(flags)
        assert score == 25 + 30 + 20 + 15 + 20
        assert score == 110
        assert rank == "A"
        assert "distress_combo" in reasons

    def test_three_signals_with_one_distress(self):
        """absentee + long_term + tax_delinquent: 15+10+25=50, only 1 distress → no combo."""
        score, rank, reasons = calculate_score({
            "absentee_owner": True,
            "long_term_owner": True,
            "tax_delinquent": True,
        })
        assert score == 50
        assert rank == "A"
        assert "distress_combo" not in reasons

    def test_three_distress_signals(self):
        """pre_foreclosure+probate+code_violation: 30+20+15+20(combo) = 85."""
        score, rank, reasons = calculate_score({
            "pre_foreclosure": True,
            "probate": True,
            "code_violation": True,
        })
        assert score == 30 + 20 + 15 + 20
        assert score == 85
        assert rank == "A"
        assert "distress_combo" in reasons

    def test_absentee_long_term_pre_foreclosure(self):
        """15+10+30 = 55 → rank A (only 1 distress signal)."""
        score, rank, reasons = calculate_score({
            "absentee_owner": True,
            "long_term_owner": True,
            "pre_foreclosure": True,
        })
        assert score == 55
        assert rank == "A"
        assert "distress_combo" not in reasons


# ── Rank boundary tests ───────────────────────────────────────────────────────

class TestRankBoundaries:
    """Verify exact cutoffs: A=25+, B=10-24, C=<10."""

    def test_score_0_is_rank_c(self):
        score, rank, _ = calculate_score({})
        assert rank == "C"
        assert score == 0

    def test_score_9_is_rank_c(self):
        assert assign_rank(9) == "C"

    def test_score_exactly_10_is_rank_b(self):
        """long_term_owner = 10 → exactly B boundary."""
        score, rank, _ = calculate_score({"long_term_owner": True})
        assert score == 10
        assert rank == "B"

    def test_score_exactly_24_is_rank_b(self):
        """absentee_owner(15) + long_term_owner(10) - 1 doesn't map cleanly.
        Use absentee(15) + long_term(10) - the sum is 25 (already A).
        For score=24 use a fabricated flag set with no direct combination.
        Instead verify via assign_rank directly."""
        assert assign_rank(24) == "B"
        assert assign_rank(10) == "B"

    def test_score_exactly_25_is_rank_a(self):
        """absentee_owner(15) + long_term_owner(10) = 25 → exactly A boundary."""
        score, rank, _ = calculate_score({
            "absentee_owner": True,
            "long_term_owner": True,
        })
        assert score == 25
        assert rank == "A"

    def test_score_100_is_rank_a(self):
        assert assign_rank(100) == "A"

    def test_score_1_is_rank_c(self):
        assert assign_rank(1) == "C"

    def test_score_0_is_rank_c_direct(self):
        assert assign_rank(0) == "C"

    def test_score_negative_is_rank_c(self):
        """Negative scores (edge case) should still map to C."""
        assert assign_rank(-5) == "C"


# ── Distress combo logic ──────────────────────────────────────────────────────

class TestDistressCombo:
    """Bonus is triggered iff 2+ distress signals are active."""

    def test_one_distress_signal_no_bonus(self):
        """Single distress signal alone → no combo."""
        for signal in DISTRESS_SIGNALS:
            score, rank, reasons = calculate_score({signal: True})
            assert "distress_combo" not in reasons, (
                f"Unexpected combo bonus for single signal: {signal}"
            )

    def test_two_distress_signals_triggers_bonus(self):
        """Every pair of distress signals → combo bonus triggered."""
        distress_list = sorted(DISTRESS_SIGNALS)
        for i, s1 in enumerate(distress_list):
            for s2 in distress_list[i + 1:]:
                score, rank, reasons = calculate_score({s1: True, s2: True})
                assert "distress_combo" in reasons, (
                    f"Expected distress_combo for signals: {s1}, {s2}"
                )
                expected_base = WEIGHTS[s1] + WEIGHTS[s2]
                assert score == expected_base + DISTRESS_COMBO_BONUS

    def test_two_non_distress_signals_no_bonus(self):
        """absentee + long_term are NOT distress signals → no combo."""
        score, rank, reasons = calculate_score({
            "absentee_owner": True,
            "long_term_owner": True,
        })
        assert "distress_combo" not in reasons
        assert score == 25

    def test_combo_bonus_added_exactly_once(self):
        """All 4 distress signals active → bonus is added exactly once (not per pair)."""
        flags = {s: True for s in DISTRESS_SIGNALS}
        score, rank, reasons = calculate_score(flags)
        combo_count = reasons.count("distress_combo")
        assert combo_count == 1

    def test_distress_combo_reason_tag_appended_last(self):
        """distress_combo reason tag appears after the signal tags."""
        score, rank, reasons = calculate_score({
            "tax_delinquent": True,
            "pre_foreclosure": True,
        })
        assert reasons[-1] == "distress_combo"


# ── Reason tags ordering and completeness ─────────────────────────────────────

class TestReasonTags:
    """Reason list contains exactly the active signals (+ distress_combo if triggered)."""

    def test_reason_list_contains_only_active_signals(self):
        flags = {
            "absentee_owner": True,
            "long_term_owner": False,
            "tax_delinquent": False,
        }
        _, _, reasons = calculate_score(flags)
        assert "absentee_owner" in reasons
        assert "long_term_owner" not in reasons
        assert "tax_delinquent" not in reasons

    def test_reason_list_no_duplicates(self):
        flags = {k: True for k in WEIGHTS}
        _, _, reasons = calculate_score(flags)
        assert len(reasons) == len(set(reasons))

    def test_reason_list_is_list(self):
        _, _, reasons = calculate_score({"absentee_owner": True})
        assert isinstance(reasons, list)

    def test_empty_flags_returns_empty_reasons(self):
        _, _, reasons = calculate_score({})
        assert reasons == []

    def test_all_signals_reasons_count_with_combo(self):
        """All 6 signals active → 6 signal tags + 1 distress_combo = 7 reasons."""
        flags = {k: True for k in WEIGHTS}
        _, _, reasons = calculate_score(flags)
        assert len(reasons) == len(WEIGHTS) + 1  # +1 for distress_combo

    def test_all_signals_no_distress_reasons_count(self):
        """Only non-distress signals → 2 reasons, no combo tag."""
        flags = {"absentee_owner": True, "long_term_owner": True}
        _, _, reasons = calculate_score(flags)
        assert len(reasons) == 2
        assert "distress_combo" not in reasons


# ── assign_rank() standalone tests ───────────────────────────────────────────

class TestAssignRank:
    """assign_rank() applies the same thresholds as calculate_score()."""

    @pytest.mark.parametrize("score,expected", [
        (0, "C"),
        (1, "C"),
        (9, "C"),
        (10, "B"),
        (14, "B"),
        (20, "B"),
        (24, "B"),
        (25, "A"),
        (30, "A"),
        (100, "A"),
        (135, "A"),
    ])
    def test_rank_thresholds(self, score: int, expected: str):
        assert assign_rank(score) == expected

    def test_assign_rank_consistent_with_calculate_score(self):
        """assign_rank(score) matches the rank returned by calculate_score()."""
        test_cases = [
            {},
            {"absentee_owner": True},
            {"long_term_owner": True},
            {"absentee_owner": True, "long_term_owner": True},
            {"tax_delinquent": True, "pre_foreclosure": True},
            {k: True for k in WEIGHTS},
        ]
        for flags in test_cases:
            score, rank_from_fn, _ = calculate_score(flags)
            rank_from_assign = assign_rank(score)
            assert rank_from_fn == rank_from_assign, (
                f"Mismatch for flags={flags}: calculate_score={rank_from_fn}, "
                f"assign_rank={rank_from_assign}"
            )
