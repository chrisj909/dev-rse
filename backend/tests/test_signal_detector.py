"""
Tests for app/services/signal_detector.py — Sprint 2, Tasks 5 & 6.

Covers:
  - detect_absentee_owner: same address, different address, missing address,
    partial match, PO Box mailing
  - detect_long_term_owner: >10yr, <10yr, exactly 10yr, missing date
  - detect_property_signals: combined convenience function
"""
from datetime import date

import pytest

from app.services.signal_detector import (
    LONG_TERM_OWNER_YEARS,
    detect_absentee_owner,
    detect_long_term_owner,
    detect_property_signals,
)


# ─────────────────────────────────────────────────────────────────────────────
# detect_absentee_owner
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectAbsenteeOwner:
    """Task 5 — Absentee owner detection."""

    def test_same_normalized_address_not_absentee(self):
        """Owner lives at the property → not absentee."""
        addr = "123 MAIN ST HOOVER AL 35244"
        assert detect_absentee_owner(addr, addr) is False

    def test_different_addresses_is_absentee(self):
        """Mailing address differs from property address → absentee."""
        prop = "123 MAIN ST HOOVER AL 35244"
        mail = "456 OAK AVE ATLANTA GA 30303"
        assert detect_absentee_owner(prop, mail) is True

    def test_po_box_mailing_is_absentee(self):
        """PO Box mailing address always differs → absentee."""
        prop = "315 PINE CT HOOVER AL 35226"
        mail = "PO BOX 4421 BIRMINGHAM AL 35203"
        assert detect_absentee_owner(prop, mail) is True

    def test_missing_mailing_address_not_flagged(self):
        """No mailing address on file → do not flag (insufficient data)."""
        assert detect_absentee_owner("123 MAIN ST HOOVER AL 35244", None) is False

    def test_empty_mailing_address_not_flagged(self):
        """Empty string mailing address → do not flag."""
        assert detect_absentee_owner("123 MAIN ST HOOVER AL 35244", "") is False

    def test_missing_property_address_not_flagged(self):
        """No property address on file → do not flag."""
        assert detect_absentee_owner(None, "456 OAK AVE ATLANTA GA 30303") is False

    def test_both_addresses_missing_not_flagged(self):
        """Both addresses missing → do not flag."""
        assert detect_absentee_owner(None, None) is False

    def test_case_insensitive_comparison(self):
        """Already-normalized addresses are compared exactly; test whitespace handling."""
        addr = "  123 MAIN ST  "
        assert detect_absentee_owner(addr, addr) is False

    def test_trailing_whitespace_stripped(self):
        """Trailing/leading whitespace should not cause a false positive."""
        addr_a = "123 MAIN ST HOOVER AL 35244  "
        addr_b = "  123 MAIN ST HOOVER AL 35244"
        assert detect_absentee_owner(addr_a, addr_b) is False

    def test_out_of_state_mailing_is_absentee(self):
        """Out-of-state mailing address → absentee."""
        prop = "558 POPLAR ST ALABASTER AL 35007"
        mail = "4509 OAKWOOD DR NASHVILLE TN 37215"
        assert detect_absentee_owner(prop, mail) is True

    def test_same_city_different_street_is_absentee(self):
        """Same city, different street → absentee (owner has investment property)."""
        prop = "208 MAGNOLIA DR HOOVER AL 35244"
        mail = "900 RIDGE RD HOOVER AL 35244"
        assert detect_absentee_owner(prop, mail) is True


# ─────────────────────────────────────────────────────────────────────────────
# detect_long_term_owner
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectLongTermOwner:
    """Task 6 — Long-term owner detection."""

    # Use a fixed reference date for deterministic tests
    REF = date(2026, 4, 1)

    def test_sale_11_years_ago_is_long_term(self):
        """Held > 10 years → long-term owner."""
        sale = date(2015, 3, 31)  # just over 11 years before REF
        assert detect_long_term_owner(sale, reference_date=self.REF) is True

    def test_sale_10_years_plus_1_day_is_long_term(self):
        """10 years + 1 day → still long-term."""
        sale = date(2016, 3, 31)
        assert detect_long_term_owner(sale, reference_date=self.REF) is True

    def test_sale_exactly_10_years_not_long_term(self):
        """Exactly 10 years to the day → NOT long-term (strictly greater than)."""
        sale = date(2016, 4, 1)  # exactly 10 years before REF
        assert detect_long_term_owner(sale, reference_date=self.REF) is False

    def test_sale_9_years_ago_not_long_term(self):
        """< 10 years → not long-term."""
        sale = date(2017, 6, 15)
        assert detect_long_term_owner(sale, reference_date=self.REF) is False

    def test_recent_sale_not_long_term(self):
        """Recent sale (2024) → not long-term."""
        sale = date(2024, 1, 15)
        assert detect_long_term_owner(sale, reference_date=self.REF) is False

    def test_very_old_sale_is_long_term(self):
        """Sale in 1991 → definitely long-term."""
        sale = date(1991, 3, 25)
        assert detect_long_term_owner(sale, reference_date=self.REF) is True

    def test_missing_sale_date_not_flagged(self):
        """None last_sale_date → do not flag (insufficient data)."""
        assert detect_long_term_owner(None, reference_date=self.REF) is False

    def test_reference_date_defaults_to_today(self):
        """Without a reference_date, defaults to date.today() — just verify it runs."""
        # Sale in 1990 → always long-term regardless of today's date
        sale = date(1990, 1, 1)
        assert detect_long_term_owner(sale) is True

    def test_sale_in_far_future_not_long_term(self):
        """A sale date in the future cannot be long-term."""
        sale = date(2030, 1, 1)
        assert detect_long_term_owner(sale, reference_date=self.REF) is False

    def test_threshold_constant_is_10(self):
        """Ensure the threshold constant is set to 10 years per BUILD_PLAN spec."""
        assert LONG_TERM_OWNER_YEARS == 10


# ─────────────────────────────────────────────────────────────────────────────
# detect_property_signals  (combined convenience function)
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectPropertySignals:
    """Combined signal detection — verify dict structure and combined outputs."""

    REF = date(2026, 4, 1)

    def test_returns_both_keys(self):
        """Result always contains absentee_owner and long_term_owner keys."""
        result = detect_property_signals(None, None, None, reference_date=self.REF)
        assert "absentee_owner" in result
        assert "long_term_owner" in result

    def test_absentee_and_long_term_both_true(self):
        """Property that is both absentee and long-term owned."""
        result = detect_property_signals(
            normalized_property_address="208 MAGNOLIA DR HOOVER AL 35244",
            normalized_mailing_address="PO BOX 4421 BIRMINGHAM AL 35203",
            last_sale_date=date(2007, 6, 22),
            reference_date=self.REF,
        )
        assert result["absentee_owner"] is True
        assert result["long_term_owner"] is True

    def test_neither_signal_active(self):
        """Recent owner-occupied property → no signals."""
        result = detect_property_signals(
            normalized_property_address="315 PINE CT HOOVER AL 35226",
            normalized_mailing_address="315 PINE CT HOOVER AL 35226",
            last_sale_date=date(2021, 9, 10),
            reference_date=self.REF,
        )
        assert result["absentee_owner"] is False
        assert result["long_term_owner"] is False

    def test_only_absentee(self):
        """Recent purchase but absentee owner."""
        result = detect_property_signals(
            normalized_property_address="329 HICKORY HILL ALABASTER AL 35007",
            normalized_mailing_address="888 COMMERCE PKWY STE 300 ATLANTA GA 30339",
            last_sale_date=date(2020, 12, 1),
            reference_date=self.REF,
        )
        assert result["absentee_owner"] is True
        assert result["long_term_owner"] is False

    def test_only_long_term(self):
        """Long-term owner who lives at the property."""
        result = detect_property_signals(
            normalized_property_address="105 CHURCH ST ALABASTER AL 35007",
            normalized_mailing_address="105 CHURCH ST ALABASTER AL 35007",
            last_sale_date=date(2003, 7, 8),
            reference_date=self.REF,
        )
        assert result["absentee_owner"] is False
        assert result["long_term_owner"] is True

    def test_missing_data_no_signals(self):
        """All None inputs → no signals active."""
        result = detect_property_signals(
            normalized_property_address=None,
            normalized_mailing_address=None,
            last_sale_date=None,
            reference_date=self.REF,
        )
        assert result["absentee_owner"] is False
        assert result["long_term_owner"] is False
