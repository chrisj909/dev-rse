"""
Tests for app/services/address_normalizer.py — Sprint 2, Task 3 verification.

Covers:
  - normalize_address: known inputs → expected canonical outputs
  - Street suffix normalization (Street→ST, Road→RD, etc.)
  - Directional normalization (North→N, etc.)
  - Unit designator normalization (Apartment→APT, Suite→STE, etc.)
  - Punctuation stripping
  - Whitespace handling
  - None / empty input handling
  - normalize_address_pair: both addresses in one call
  - addresses_match: comparison helper
"""
import pytest

from app.services.address_normalizer import (
    normalize_address,
    normalize_address_pair,
    addresses_match,
)


# ─────────────────────────────────────────────────────────────────────────────
# normalize_address — basic handling
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeAddressBasic:
    """Null/empty inputs and basic uppercase behaviour."""

    def test_none_returns_none(self):
        assert normalize_address(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_address("") is None

    def test_whitespace_only_returns_none(self):
        assert normalize_address("   ") is None

    def test_already_uppercase(self):
        result = normalize_address("123 MAIN ST")
        assert result == "123 MAIN ST"

    def test_lowercase_uppercased(self):
        result = normalize_address("123 main street")
        assert result == "123 MAIN ST"

    def test_mixed_case(self):
        result = normalize_address("123 Main Street")
        assert result == "123 MAIN ST"

    def test_leading_trailing_whitespace_stripped(self):
        result = normalize_address("  123 Main Street  ")
        assert result == "123 MAIN ST"

    def test_interior_whitespace_collapsed(self):
        result = normalize_address("123  Main   Street")
        assert result == "123 MAIN ST"


# ─────────────────────────────────────────────────────────────────────────────
# normalize_address — street suffix normalization
# ─────────────────────────────────────────────────────────────────────────────

class TestStreetSuffixes:
    """Street → ST, Road → RD, etc."""

    def test_street_to_st(self):
        assert normalize_address("123 Main Street") == "123 MAIN ST"

    def test_road_to_rd(self):
        assert normalize_address("456 Oak Hill Road") == "456 OAK HILL RD"

    def test_avenue_to_ave(self):
        assert normalize_address("789 Cedar Avenue") == "789 CEDAR AVE"

    def test_boulevard_to_blvd(self):
        assert normalize_address("100 Sunset Boulevard") == "100 SUNSET BLVD"

    def test_drive_to_dr(self):
        assert normalize_address("200 Magnolia Drive") == "200 MAGNOLIA DR"

    def test_lane_to_ln(self):
        assert normalize_address("300 Elm Lane") == "300 ELM LN"

    def test_court_to_ct(self):
        assert normalize_address("315 Pine Court") == "315 PINE CT"

    def test_place_to_pl(self):
        assert normalize_address("400 Oak Place") == "400 OAK PL"

    def test_circle_to_cir(self):
        assert normalize_address("500 Dogwood Circle") == "500 DOGWOOD CIR"

    def test_terrace_to_ter(self):
        assert normalize_address("600 Hill Terrace") == "600 HILL TER"

    def test_highway_to_hwy(self):
        assert normalize_address("328 Highway 25") == "328 HWY 25"

    def test_trail_to_trl(self):
        assert normalize_address("446 Timber Ridge Trail") == "446 TIMBER RIDGE TRL"

    def test_parkway_to_pkwy(self):
        assert normalize_address("350 Greystone Parkway") == "350 GREYSTONE PKWY"

    def test_way_unchanged(self):
        """WAY is already the abbreviation — remains WAY."""
        assert normalize_address("519 Willow Way") == "519 WILLOW WAY"


# ─────────────────────────────────────────────────────────────────────────────
# normalize_address — directional normalization
# ─────────────────────────────────────────────────────────────────────────────

class TestDirectionals:
    """North→N, South→S, East→E, West→W and compound directionals."""

    def test_north_prefix(self):
        assert normalize_address("123 North Main Street") == "123 N MAIN ST"

    def test_south_suffix(self):
        result = normalize_address("2200 Highway 31 South")
        assert result == "2200 HWY 31 S"

    def test_east_inline(self):
        assert normalize_address("9834 Peachtree Road NE") == "9834 PEACHTREE RD NE"

    def test_west_inline(self):
        assert normalize_address("600 Beacon Parkway West") == "600 BEACON PKWY W"

    def test_northwest(self):
        assert normalize_address("1800 Peachtree Street NW") == "1800 PEACHTREE ST NW"


# ─────────────────────────────────────────────────────────────────────────────
# normalize_address — unit/apartment normalization
# ─────────────────────────────────────────────────────────────────────────────

class TestUnitDesignators:
    """Apartment→APT, Suite→STE, etc."""

    def test_apartment_to_apt(self):
        assert normalize_address("123 Main Street Apartment 4") == "123 MAIN ST APT 4"

    def test_suite_to_ste(self):
        result = normalize_address("888 Commerce Pkwy Suite 300")
        assert result == "888 COMMERCE PKWY STE 300"

    def test_ste_already_abbreviated(self):
        result = normalize_address("888 Commerce Pkwy Ste 300")
        assert result == "888 COMMERCE PKWY STE 300"

    def test_unit_designation(self):
        result = normalize_address("123 Main St Unit 2B")
        assert result == "123 MAIN ST UNIT 2B"


# ─────────────────────────────────────────────────────────────────────────────
# normalize_address — punctuation stripping
# ─────────────────────────────────────────────────────────────────────────────

class TestPunctuation:
    """Commas, periods, and similar punctuation are stripped."""

    def test_comma_stripped(self):
        result = normalize_address("123 Main Street, Hoover AL 35244")
        assert result == "123 MAIN ST HOOVER AL 35244"

    def test_period_stripped(self):
        result = normalize_address("P.O. Box 99")
        assert "." not in result

    def test_multiple_punctuation(self):
        result = normalize_address("123 Main St., Apt. 4, Birmingham, AL")
        assert "," not in result
        assert result.count(".") == 0


# ─────────────────────────────────────────────────────────────────────────────
# normalize_address — real Shelby County address examples
# ─────────────────────────────────────────────────────────────────────────────

class TestRealWorldExamples:
    """Round-trip checks on actual sample CSV addresses."""

    def test_owner_occupied_property(self):
        """124 Oak Street Hoover AL 35244 → canonical form."""
        result = normalize_address("124 Oak Street Hoover AL 35244")
        assert result == "124 OAK ST HOOVER AL 35244"

    def test_po_box(self):
        result = normalize_address("PO Box 4421 Birmingham AL 35203")
        assert "PO" in result
        assert "BOX" in result
        assert "BIRMINGHAM" in result

    def test_out_of_state_mailing(self):
        result = normalize_address("4509 Oakwood Dr Nashville TN 37215")
        assert result == "4509 OAKWOOD DR NASHVILLE TN 37215"

    def test_corporate_suite_address(self):
        result = normalize_address("888 Commerce Pkwy Suite 300 Atlanta GA 30339")
        assert "STE 300" in result
        assert "ATLANTA" in result

    def test_highway_address(self):
        result = normalize_address("2200 Highway 31 South Suite 101 Pelham AL 35124")
        assert "HWY 31" in result
        assert "STE 101" in result


# ─────────────────────────────────────────────────────────────────────────────
# normalize_address_pair
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeAddressPair:
    """Convenience function that normalizes both addresses in one call."""

    def test_both_normalized(self):
        prop, mail = normalize_address_pair("123 Main Street", "456 Oak Avenue")
        assert prop == "123 MAIN ST"
        assert mail == "456 OAK AVE"

    def test_none_property(self):
        prop, mail = normalize_address_pair(None, "456 Oak Avenue")
        assert prop is None
        assert mail == "456 OAK AVE"

    def test_none_mailing(self):
        prop, mail = normalize_address_pair("123 Main Street", None)
        assert prop == "123 MAIN ST"
        assert mail is None

    def test_both_none(self):
        prop, mail = normalize_address_pair(None, None)
        assert prop is None
        assert mail is None


# ─────────────────────────────────────────────────────────────────────────────
# addresses_match
# ─────────────────────────────────────────────────────────────────────────────

class TestAddressesMatch:
    """Compare two normalized addresses."""

    def test_same_address_matches(self):
        addr = "123 MAIN ST HOOVER AL 35244"
        assert addresses_match(addr, addr) is True

    def test_different_addresses_no_match(self):
        assert addresses_match("123 MAIN ST", "456 OAK AVE") is False

    def test_none_a_no_match(self):
        assert addresses_match(None, "123 MAIN ST") is False

    def test_none_b_no_match(self):
        assert addresses_match("123 MAIN ST", None) is False

    def test_both_none_no_match(self):
        assert addresses_match(None, None) is False

    def test_whitespace_difference_matches(self):
        """Trailing/leading whitespace should still match."""
        assert addresses_match("  123 MAIN ST  ", "123 MAIN ST") is True
