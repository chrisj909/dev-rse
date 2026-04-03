"""
RSE Scoring Weights — Sprint 3, Task 9
app/scoring/weights.py

Versioned weight definitions for the scoring engine.

Version string is stored on every score row so we can recompute
or compare across weight versions in the future.

Signal weights (v1):
  absentee_owner:  +15
  long_term_owner: +10
  tax_delinquent:  +25  (placeholder — no data yet)
  pre_foreclosure: +30  (placeholder)
  probate:         +20  (placeholder)
  code_violation:  +15  (placeholder)
  Distress combo:  +20 bonus (when 2+ distress signals are active)

Distress signals = {tax_delinquent, pre_foreclosure, probate, code_violation}

Ranks:
  A = 25+
  B = 15–24
  C = <15
"""
from __future__ import annotations

# ── Version ───────────────────────────────────────────────────────────────────
SCORING_VERSION: str = "v1"

# ── Signal weights: signal_name → points awarded if flag is True ──────────────
WEIGHTS: dict[str, int] = {
    "absentee_owner":  15,
    "long_term_owner": 10,
    "tax_delinquent":  25,
    "pre_foreclosure": 30,
    "probate":         20,
    "code_violation":  15,
}

# ── Distress combo bonus ──────────────────────────────────────────────────────
# When 2 or more distress signals are active, add a bonus score.
# Distress signals are those that indicate active financial / legal pressure.
DISTRESS_SIGNALS: frozenset[str] = frozenset({
    "tax_delinquent",
    "pre_foreclosure",
    "probate",
    "code_violation",
})
DISTRESS_COMBO_BONUS: int = 20
DISTRESS_COMBO_THRESHOLD: int = 2

# ── Rank thresholds ───────────────────────────────────────────────────────────
RANK_A_MIN: int = 25   # score >= 25 → rank A
RANK_B_MIN: int = 15   # score >= 15 → rank B; score < 15 → rank C


# ── Core scoring function ─────────────────────────────────────────────────────

def calculate_score(flags: dict[str, bool]) -> tuple[int, str, list[str]]:
    """
    Calculate the weighted score, rank, and reason tags for a signal dict.

    This function is pure (no side effects) and stateless — safe to call
    from tests, scripts, or the ScoringEngine without a DB session.

    Args:
        flags: Dict mapping signal_name → bool.
               Keys not in WEIGHTS are silently ignored.
               Missing keys default to False.

    Returns:
        (score, rank, reasons) where:
          score:   int — total weighted score (including any combo bonus)
          rank:    str — "A", "B", or "C"
          reasons: list[str] — ordered list of active signal tags that
                   contributed to the score, plus "distress_combo" if
                   the bonus was triggered. Reason order follows WEIGHTS
                   key order (insertion order, Python 3.7+).

    Examples:
        >>> calculate_score({})
        (0, 'C', [])

        >>> calculate_score({"absentee_owner": True})
        (15, 'B', ['absentee_owner'])

        >>> calculate_score({"absentee_owner": True, "long_term_owner": True})
        (25, 'A', ['absentee_owner', 'long_term_owner'])

        >>> calculate_score({"tax_delinquent": True, "pre_foreclosure": True})
        (75, 'A', ['tax_delinquent', 'pre_foreclosure', 'distress_combo'])
    """
    score: int = 0
    reasons: list[str] = []

    # Sum weights for all active signals (preserve WEIGHTS key order)
    for signal_name, weight in WEIGHTS.items():
        if flags.get(signal_name, False):
            score += weight
            reasons.append(signal_name)

    # Distress combo bonus: 2+ distress signals active
    active_distress = [s for s in DISTRESS_SIGNALS if flags.get(s, False)]
    if len(active_distress) >= DISTRESS_COMBO_THRESHOLD:
        score += DISTRESS_COMBO_BONUS
        reasons.append("distress_combo")

    # Assign rank
    if score >= RANK_A_MIN:
        rank = "A"
    elif score >= RANK_B_MIN:
        rank = "B"
    else:
        rank = "C"

    return score, rank, reasons


def assign_rank(score: int) -> str:
    """
    Assign a rank string given a raw integer score.

    Exposed separately so callers that already have a score can re-rank
    without re-running the full calculate_score pipeline.

    Args:
        score: Integer score value.

    Returns:
        "A", "B", or "C"
    """
    if score >= RANK_A_MIN:
        return "A"
    elif score >= RANK_B_MIN:
        return "B"
    return "C"
