"""Mode-aware scoring weights and rank thresholds."""
from __future__ import annotations

from dataclasses import dataclass

# ── Version ───────────────────────────────────────────────────────────────────
SCORING_VERSION: str = "v3"


@dataclass(frozen=True)
class ScoringModeConfig:
    slug: str
    label: str
    description: str
    weights: dict[str, int]
    rank_a_min: int
    rank_b_min: int
    distress_combo_bonus: int
    distress_combo_threshold: int


DEFAULT_SCORING_MODE: str = "broad"

SCORING_MODES: dict[str, ScoringModeConfig] = {
    "broad": ScoringModeConfig(
        slug="broad",
        label="Broad",
        description="Blended opportunity mode across seller and investor use cases.",
        weights={
            "absentee_owner": 15,
            "long_term_owner": 10,
            "out_of_state_owner": 12,
            "corporate_owner": 8,
            "tax_delinquent": 25,
            "pre_foreclosure": 30,
            "probate": 20,
            "code_violation": 15,
        },
        rank_a_min=25,
        rank_b_min=10,
        distress_combo_bonus=20,
        distress_combo_threshold=2,
    ),
    "owner_occupant": ScoringModeConfig(
        slug="owner_occupant",
        label="Owner-Occupant Seller",
        description="Prioritize homeowner-style distress and long tenure over investor ownership patterns.",
        weights={
            "absentee_owner": 2,
            "long_term_owner": 18,
            "out_of_state_owner": 0,
            "corporate_owner": 0,
            "tax_delinquent": 30,
            "pre_foreclosure": 35,
            "probate": 25,
            "code_violation": 18,
        },
        rank_a_min=30,
        rank_b_min=12,
        distress_combo_bonus=25,
        distress_combo_threshold=2,
    ),
    "investor": ScoringModeConfig(
        slug="investor",
        label="Investor Acquisition",
        description="Prioritize absentee, out-of-state, and portfolio-style ownership alongside distress.",
        weights={
            "absentee_owner": 18,
            "long_term_owner": 8,
            "out_of_state_owner": 15,
            "corporate_owner": 10,
            "tax_delinquent": 28,
            "pre_foreclosure": 25,
            "probate": 18,
            "code_violation": 12,
        },
        rank_a_min=28,
        rank_b_min=12,
        distress_combo_bonus=18,
        distress_combo_threshold=2,
    ),
}


def get_scoring_mode(mode: str | None = None) -> ScoringModeConfig:
    normalized = (mode or DEFAULT_SCORING_MODE).strip().lower()
    if normalized not in SCORING_MODES:
        raise ValueError(f"Unsupported scoring mode: {mode}")
    return SCORING_MODES[normalized]


# ── Backward-compatible broad-mode aliases ───────────────────────────────────
WEIGHTS: dict[str, int] = SCORING_MODES[DEFAULT_SCORING_MODE].weights

# ── Distress combo bonus ──────────────────────────────────────────────────────
# When 2 or more distress signals are active, add a bonus score.
# Distress signals are those that indicate active financial / legal pressure.
DISTRESS_SIGNALS: frozenset[str] = frozenset({
    "tax_delinquent",
    "pre_foreclosure",
    "probate",
    "code_violation",
})
DISTRESS_COMBO_BONUS: int = SCORING_MODES[DEFAULT_SCORING_MODE].distress_combo_bonus
DISTRESS_COMBO_THRESHOLD: int = SCORING_MODES[DEFAULT_SCORING_MODE].distress_combo_threshold

# ── Rank thresholds ───────────────────────────────────────────────────────────
RANK_A_MIN: int = SCORING_MODES[DEFAULT_SCORING_MODE].rank_a_min
RANK_B_MIN: int = SCORING_MODES[DEFAULT_SCORING_MODE].rank_b_min


# ── Core scoring function ─────────────────────────────────────────────────────

def calculate_score_for_mode(
    flags: dict[str, bool],
    mode: str = DEFAULT_SCORING_MODE,
) -> tuple[int, str, list[str]]:
    """Calculate the weighted score, rank, and reason tags for a scoring mode."""
    config = get_scoring_mode(mode)
    score: int = 0
    reasons: list[str] = []

    for signal_name, weight in config.weights.items():
        if flags.get(signal_name, False):
            score += weight
            reasons.append(signal_name)

    active_distress = [s for s in DISTRESS_SIGNALS if flags.get(s, False)]
    if len(active_distress) >= config.distress_combo_threshold:
        score += config.distress_combo_bonus
        reasons.append("distress_combo")

    if score >= config.rank_a_min:
        rank = "A"
    elif score >= config.rank_b_min:
        rank = "B"
    else:
        rank = "C"

    return score, rank, reasons


def calculate_score(flags: dict[str, bool]) -> tuple[int, str, list[str]]:
    """Backward-compatible broad-mode scoring helper."""
    return calculate_score_for_mode(flags, mode=DEFAULT_SCORING_MODE)


def assign_rank(score: int, mode: str = DEFAULT_SCORING_MODE) -> str:
    """Assign a rank string for the configured scoring mode."""
    config = get_scoring_mode(mode)
    if score >= config.rank_a_min:
        return "A"
    elif score >= config.rank_b_min:
        return "B"
    return "C"
