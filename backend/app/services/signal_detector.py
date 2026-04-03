"""
RSE Signal Detector — Sprint 2 (Tasks 5 & 6)
app/services/signal_detector.py

Pure functions that detect signals from property data.
Each detector is stateless and recomputable from property fields alone.
Returns a bool — no DB writes here; callers write to the signals table.

Design rules (from BUILD_PLAN):
  - Signals are stateless: no signal depends on another.
  - Missing / None data → conservatively return False (not enough info to flag).
  - Normalized addresses are used for comparison (never raw).
"""
from datetime import date
from typing import Optional


# ── Constants ─────────────────────────────────────────────────────────────────

LONG_TERM_OWNER_YEARS: int = 10  # threshold in years


# ── Task 5: Absentee Owner Detection ─────────────────────────────────────────

def detect_absentee_owner(
    normalized_property_address: Optional[str],
    normalized_mailing_address: Optional[str],
) -> bool:
    """
    Detect absentee ownership by comparing the normalized property address
    to the normalized mailing address.

    Rule:
      - If the two addresses differ → absentee owner (owner lives elsewhere).
      - If mailing address is missing/blank → return False (insufficient data,
        we will not falsely flag someone as absent).
      - If property address is missing → return False.

    Args:
        normalized_property_address: The canonical property address string
            (already passed through normalize_address()).
        normalized_mailing_address:  The canonical mailing address string
            (already passed through normalize_address()).

    Returns:
        True if the owner is absentee, False otherwise.

    Examples:
        >>> detect_absentee_owner("123 MAIN ST HOOVER AL 35244", "PO BOX 99 ATLANTA GA 30303")
        True
        >>> detect_absentee_owner("123 MAIN ST HOOVER AL 35244", "123 MAIN ST HOOVER AL 35244")
        False
        >>> detect_absentee_owner("123 MAIN ST HOOVER AL 35244", None)
        False
    """
    if not normalized_property_address or not normalized_mailing_address:
        return False  # Insufficient data — do not flag
    return normalized_property_address.strip() != normalized_mailing_address.strip()


# ── Task 6: Long-Term Owner Detection ────────────────────────────────────────

def detect_long_term_owner(
    last_sale_date: Optional[date],
    reference_date: Optional[date] = None,
) -> bool:
    """
    Detect long-term ownership: last sale was more than LONG_TERM_OWNER_YEARS
    (10) years before the reference date (defaults to today).

    Rule:
      - If last_sale_date is None/missing → return False (insufficient data).
      - If (reference_date − last_sale_date) > 10 years → True.
      - Exactly 10 years is NOT flagged (strictly greater than).

    Args:
        last_sale_date:  The date of the last recorded sale for the property.
                         May be None if the record has no sale date.
        reference_date:  The date to measure from. Defaults to date.today().
                         Primarily exposed for unit-test determinism.

    Returns:
        True if the owner has held the property for more than 10 years.

    Examples:
        >>> from datetime import date
        >>> detect_long_term_owner(date(2010, 1, 1), reference_date=date(2026, 4, 1))
        True
        >>> detect_long_term_owner(date(2020, 1, 1), reference_date=date(2026, 4, 1))
        False
        >>> detect_long_term_owner(None)
        False
    """
    if last_sale_date is None:
        return False  # Missing data — do not flag

    today = reference_date or date.today()

    # Use fractional days for an accurate comparison that handles leap years.
    days_held = (today - last_sale_date).days
    years_held = days_held / 365.25

    return years_held > LONG_TERM_OWNER_YEARS


# ── Convenience: detect both signals in one call ──────────────────────────────

def detect_property_signals(
    normalized_property_address: Optional[str],
    normalized_mailing_address: Optional[str],
    last_sale_date: Optional[date],
    reference_date: Optional[date] = None,
) -> dict[str, bool]:
    """
    Run both MVP signal detectors for a single property and return a dict
    of signal_name → bool.

    This is the primary entry point used by the ingestion script and
    (later) the SignalEngine. The dict structure intentionally mirrors the
    Signal ORM model's column names so callers can spread it directly.

    Args:
        normalized_property_address: Canonical property address.
        normalized_mailing_address:  Canonical mailing address.
        last_sale_date:              Date of last recorded sale.
        reference_date:              Date to measure long-term threshold from.

    Returns:
        {
            "absentee_owner": bool,
            "long_term_owner": bool,
        }
    """
    return {
        "absentee_owner": detect_absentee_owner(
            normalized_property_address,
            normalized_mailing_address,
        ),
        "long_term_owner": detect_long_term_owner(
            last_sale_date,
            reference_date=reference_date,
        ),
    }
