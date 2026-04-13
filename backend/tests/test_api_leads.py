"""
Tests for the Lead API endpoints — Sprint 5, Tasks 11 & 12.
app/api/leads.py

Strategy:
  - No live database required. The DB session is mocked via conftest fixtures.
  - session.execute() is mocked with side_effect lists to return controlled
    data for the data query + the count query on each endpoint call.
  - Tests cover response shapes, filtering params, edge cases, and HTTP status codes.

Covers:
  GET /api/leads/top
    - Empty DB → {"leads": [], "total": 0}
    - Returns correct leads list with proper field names
    - Response shape: all required fields present
    - Signals list contains only active signal names
    - No signals → empty signals list
    - All signals active → all signal names in list
    - min_score filter applied
    - absentee_owner filter (True)
    - absentee_owner filter (False)
    - long_term_owner filter (True)
    - long_term_owner filter (False)
    - city filter
    - Combined filters
    - limit default (50)
    - limit custom value
    - limit clamped: > 200 → 422 Unprocessable Entity
    - limit < 1 → 422
    - min_score < 0 → 422
    - Multiple leads returned in score-desc order
    - total count reflects all matching records
    - Rank A, B, C values preserved
    - score=0 returns correctly
    - owner_name null → null in response
    - address null → null in response
    - city null → null in response
    - zip null → null in response
    - state defaults to AL
    - last_updated ISO format in response

  GET /api/leads/new
    - Empty DB → {"leads": [], "total": 0}
    - Returns leads from last 7 days
    - Response shape matches LeadsListResponse
    - limit parameter respected
    - limit > 200 → 422
    - limit < 1 → 422
    - Signals list in new-leads response
    - Multiple leads ordered by last_updated desc

  GET /api/property/{id}
    - Valid UUID, property found → 200 with PropertyDetailResponse
    - Invalid UUID (not UUID format) → 400
    - Valid UUID, property not found → 404
    - Response contains all signal boolean fields
    - Response contains full score detail (score, rank, reason, version)
    - All signal booleans False when no signals active
    - Signal booleans match ORM row values
    - Null optional fields (owner_name, address, etc.) handled
    - assessed_value null → null in response
    - last_sale_date null → null in response
    - raw_address present in detail response
    - mailing_address present in detail response
    - scoring_version preserved in response
    - reason list preserved in response
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import make_mock_property, make_mock_score, make_mock_signal


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_data_result(rows: list) -> MagicMock:
    """Wrap rows in a mock CursorResult that responds to .all()."""
    result = MagicMock()
    result.all.return_value = rows
    return result


def _make_count_result(count: int) -> MagicMock:
    """Wrap count in a mock CursorResult that responds to .scalar()."""
    result = MagicMock()
    result.scalar.return_value = count
    return result


def _make_one_result(row) -> MagicMock:
    """Wrap a single row in a mock CursorResult that responds to .one_or_none()."""
    result = MagicMock()
    result.one_or_none.return_value = row
    return result


def _setup_list_mock(mock_session, rows, count):
    """Configure mock_session.execute with two side-effects: rows then count."""
    mock_session.execute.side_effect = [
        _make_data_result(rows),
        _make_count_result(count),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
#  GET /api/leads/top
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetTopLeadsEmpty:
    """Edge case: no properties in DB → empty response."""

    def test_returns_200(self, test_client, mock_session):
        _setup_list_mock(mock_session, rows=[], count=0)
        resp = test_client.get("/api/leads/top")
        assert resp.status_code == 200

    def test_leads_is_empty_list(self, test_client, mock_session):
        _setup_list_mock(mock_session, rows=[], count=0)
        data = test_client.get("/api/leads/top").json()
        assert data["leads"] == []

    def test_total_is_zero(self, test_client, mock_session):
        _setup_list_mock(mock_session, rows=[], count=0)
        data = test_client.get("/api/leads/top").json()
        assert data["total"] == 0

    def test_response_has_leads_key(self, test_client, mock_session):
        _setup_list_mock(mock_session, rows=[], count=0)
        data = test_client.get("/api/leads/top").json()
        assert "leads" in data

    def test_response_has_total_key(self, test_client, mock_session):
        _setup_list_mock(mock_session, rows=[], count=0)
        data = test_client.get("/api/leads/top").json()
        assert "total" in data


class TestGetTopLeadsWithData:
    """Successful responses with lead data."""

    def _make_row(self, **kwargs):
        prop_id = uuid.uuid4()
        prop = make_mock_property(prop_id=prop_id, **kwargs)
        sig = make_mock_signal(property_id=prop_id, absentee_owner=True, long_term_owner=True)
        score = make_mock_score(property_id=prop_id, score=25, rank="A")
        return prop, sig, score

    def test_returns_correct_count(self, test_client, mock_session):
        row = self._make_row()
        _setup_list_mock(mock_session, rows=[row], count=1)
        data = test_client.get("/api/leads/top").json()
        assert len(data["leads"]) == 1

    def test_total_reflects_all_matching(self, test_client, mock_session):
        row = self._make_row()
        # 100 total but limit returns 1
        _setup_list_mock(mock_session, rows=[row], count=100)
        data = test_client.get("/api/leads/top").json()
        assert data["total"] == 100

    def test_lead_has_property_id(self, test_client, mock_session):
        prop_id = uuid.uuid4()
        prop = make_mock_property(prop_id=prop_id)
        sig = make_mock_signal(property_id=prop_id)
        sc = make_mock_score(property_id=prop_id)
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["property_id"] == str(prop_id)

    def test_lead_has_parcel_id(self, test_client, mock_session):
        prop = make_mock_property(parcel_id="SC-PARCEL-999")
        sig = make_mock_signal()
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["parcel_id"] == "SC-PARCEL-999"

    def test_lead_has_county(self, test_client, mock_session):
        prop = make_mock_property(county="jefferson")
        sig = make_mock_signal()
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["county"] == "jefferson"

    def test_lead_has_address(self, test_client, mock_session):
        prop = make_mock_property(address="789 ELM AVE")
        sig = make_mock_signal()
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["address"] == "789 ELM AVE"

    def test_lead_has_city(self, test_client, mock_session):
        prop = make_mock_property(city="BIRMINGHAM")
        sig = make_mock_signal()
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["city"] == "BIRMINGHAM"

    def test_lead_has_state(self, test_client, mock_session):
        prop = make_mock_property(state="AL")
        sig = make_mock_signal()
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["state"] == "AL"

    def test_lead_has_zip(self, test_client, mock_session):
        prop = make_mock_property(zip_code="35244")
        sig = make_mock_signal()
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["zip"] == "35244"

    def test_lead_has_owner_name(self, test_client, mock_session):
        prop = make_mock_property(owner_name="JANE SMITH")
        sig = make_mock_signal()
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["owner_name"] == "JANE SMITH"

    def test_lead_has_assessed_value(self, test_client, mock_session):
        prop = make_mock_property(assessed_value=215000.0)
        sig = make_mock_signal()
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["assessed_value"] == 215000.0

    def test_lead_has_score(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal()
        sc = make_mock_score(score=35)
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["score"] == 35

    def test_lead_has_rank(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal()
        sc = make_mock_score(rank="B")
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["rank"] == "B"

    def test_lead_has_signals_list(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal()
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert "signals" in lead
        assert isinstance(lead["signals"], list)

    def test_lead_has_last_updated(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal()
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert "last_updated" in lead
        assert lead["last_updated"] is not None

    def test_missing_state_defaults_to_al(self, test_client, mock_session):
        prop = make_mock_property(state=None)
        sig = make_mock_signal()
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads").json()["leads"][0]
        assert lead["state"] == "AL"

    def test_missing_rank_and_last_updated_are_coerced(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal()
        sc = make_mock_score(rank=None, last_updated=None)
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads").json()["leads"][0]
        assert lead["rank"] == "C"
        assert lead["last_updated"] is not None

    def test_multiple_leads_returned(self, test_client, mock_session):
        rows = [
            (make_mock_property(parcel_id=f"SC-{i}"), make_mock_signal(), make_mock_score(score=30 - i))
            for i in range(3)
        ]
        _setup_list_mock(mock_session, rows=rows, count=3)
        data = test_client.get("/api/leads/top").json()
        assert len(data["leads"]) == 3

    def test_rank_a_preserved(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal()
        sc = make_mock_score(score=40, rank="A")
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["rank"] == "A"

    def test_rank_b_preserved(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal()
        sc = make_mock_score(score=20, rank="B")
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["rank"] == "B"

    def test_rank_c_preserved(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal()
        sc = make_mock_score(score=5, rank="C")
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["rank"] == "C"

    def test_score_zero_handled(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal()
        sc = make_mock_score(score=0, rank="C", reason=[])
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["score"] == 0

    def test_owner_name_null(self, test_client, mock_session):
        prop = make_mock_property(owner_name=None)
        sig = make_mock_signal()
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["owner_name"] is None

    def test_address_falls_back_to_mailing_address(self, test_client, mock_session):
        prop = make_mock_property(address=None, raw_address=None, mailing_address="456 OTHER ST")
        sig = make_mock_signal()
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["address"] == "456 OTHER ST"

    def test_address_falls_back_to_raw_address(self, test_client, mock_session):
        prop = make_mock_property(address=None, raw_address="123 Main Street", mailing_address=None)
        sig = make_mock_signal()
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["address"] == "123 Main Street"

    def test_city_null(self, test_client, mock_session):
        prop = make_mock_property(city=None)
        sig = make_mock_signal()
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["city"] is None

    def test_zip_null(self, test_client, mock_session):
        prop = make_mock_property(zip_code=None)
        sig = make_mock_signal()
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["zip"] is None

    def test_assessed_value_null(self, test_client, mock_session):
        prop = make_mock_property(assessed_value=None)
        sig = make_mock_signal()
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["assessed_value"] is None


class TestGetTopLeadsSignals:
    """Signal list construction in /leads/top response."""

    def test_no_signals_active_returns_empty_list(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal()  # all False
        sc = make_mock_score(score=0, rank="C", reason=[])
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["signals"] == []

    def test_absentee_owner_active_in_signals(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal(absentee_owner=True)
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert "absentee_owner" in lead["signals"]

    def test_long_term_owner_active_in_signals(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal(long_term_owner=True)
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert "long_term_owner" in lead["signals"]

    def test_tax_delinquent_active_in_signals(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal(tax_delinquent=True)
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert "tax_delinquent" in lead["signals"]

    def test_multiple_signals_active(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal(absentee_owner=True, long_term_owner=True, tax_delinquent=True)
        sc = make_mock_score(score=50, rank="A")
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert "absentee_owner" in lead["signals"]
        assert "long_term_owner" in lead["signals"]
        assert "tax_delinquent" in lead["signals"]

    def test_inactive_signals_not_in_list(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal(absentee_owner=True)  # only this one is True
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert "long_term_owner" not in lead["signals"]
        assert "tax_delinquent" not in lead["signals"]

    def test_all_signals_active(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal(
            absentee_owner=True,
            long_term_owner=True,
            out_of_state_owner=True,
            corporate_owner=True,
            tax_delinquent=True,
            pre_foreclosure=True,
            probate=True,
            eviction=True,
            code_violation=True,
        )
        sc = make_mock_score(score=100, rank="A")
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        expected = {
            "absentee_owner", "long_term_owner", "out_of_state_owner", "corporate_owner",
            "tax_delinquent", "pre_foreclosure", "probate", "eviction", "code_violation",
        }
        assert set(lead["signals"]) == expected

    def test_signals_order_is_canonical(self, test_client, mock_session):
        """Active signals should follow the canonical field order."""
        prop = make_mock_property()
        sig = make_mock_signal(absentee_owner=True, long_term_owner=True)
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/top").json()["leads"][0]
        assert lead["signals"].index("absentee_owner") < lead["signals"].index("long_term_owner")


class TestGetTopLeadsFiltering:
    """Query parameter filtering on /leads/top."""

    def _empty(self, mock_session):
        _setup_list_mock(mock_session, rows=[], count=0)

    def test_min_score_accepted(self, test_client, mock_session):
        self._empty(mock_session)
        resp = test_client.get("/api/leads/top?min_score=20")
        assert resp.status_code == 200

    def test_absentee_owner_true_accepted(self, test_client, mock_session):
        self._empty(mock_session)
        resp = test_client.get("/api/leads/top?absentee_owner=true")
        assert resp.status_code == 200

    def test_absentee_owner_false_accepted(self, test_client, mock_session):
        self._empty(mock_session)
        resp = test_client.get("/api/leads/top?absentee_owner=false")
        assert resp.status_code == 200

    def test_long_term_owner_true_accepted(self, test_client, mock_session):
        self._empty(mock_session)
        resp = test_client.get("/api/leads/top?long_term_owner=true")
        assert resp.status_code == 200

    def test_long_term_owner_false_accepted(self, test_client, mock_session):
        self._empty(mock_session)
        resp = test_client.get("/api/leads/top?long_term_owner=false")
        assert resp.status_code == 200

    def test_city_filter_accepted(self, test_client, mock_session):
        self._empty(mock_session)
        resp = test_client.get("/api/leads/top?city=HOOVER")
        assert resp.status_code == 200

    def test_county_filter_accepted(self, test_client, mock_session):
        self._empty(mock_session)
        resp = test_client.get("/api/leads/top?county=jefferson")
        assert resp.status_code == 200

    def test_combined_filters_accepted(self, test_client, mock_session):
        self._empty(mock_session)
        resp = test_client.get(
            "/api/leads/top?min_score=15&absentee_owner=true&long_term_owner=true&city=HOOVER"
        )
        assert resp.status_code == 200

    def test_min_score_negative_rejected(self, test_client, mock_session):
        resp = test_client.get("/api/leads/top?min_score=-1")
        assert resp.status_code == 422

    def test_filters_return_filtered_results(self, test_client, mock_session):
        """Mock DB returns one result; verify it appears in response."""
        prop = make_mock_property(city="HOOVER")
        sig = make_mock_signal(absentee_owner=True)
        sc = make_mock_score(score=30, rank="A")
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        data = test_client.get("/api/leads/top?min_score=20&absentee_owner=true&city=HOOVER").json()
        assert len(data["leads"]) == 1
        assert data["leads"][0]["city"] == "HOOVER"


class TestGetTopLeadsLimit:
    """Limit parameter validation on /leads/top."""

    def test_default_limit_accepted(self, test_client, mock_session):
        _setup_list_mock(mock_session, rows=[], count=0)
        resp = test_client.get("/api/leads/top")
        assert resp.status_code == 200

    def test_limit_1_accepted(self, test_client, mock_session):
        _setup_list_mock(mock_session, rows=[], count=0)
        resp = test_client.get("/api/leads/top?limit=1")
        assert resp.status_code == 200

    def test_limit_200_accepted(self, test_client, mock_session):
        _setup_list_mock(mock_session, rows=[], count=0)
        resp = test_client.get("/api/leads/top?limit=200")
        assert resp.status_code == 200

    def test_limit_250_accepted(self, test_client, mock_session):
        _setup_list_mock(mock_session, rows=[], count=0)
        resp = test_client.get("/api/leads/top?limit=250")
        assert resp.status_code == 200

    def test_limit_251_rejected(self, test_client, mock_session):
        resp = test_client.get("/api/leads/top?limit=251")
        assert resp.status_code == 422

    def test_limit_0_rejected(self, test_client, mock_session):
        resp = test_client.get("/api/leads/top?limit=0")
        assert resp.status_code == 422

    def test_limit_negative_rejected(self, test_client, mock_session):
        resp = test_client.get("/api/leads/top?limit=-5")
        assert resp.status_code == 422

    def test_limit_100_returns_up_to_100(self, test_client, mock_session):
        rows = [
            (make_mock_property(parcel_id=f"SC-{i}"), make_mock_signal(), make_mock_score(score=50))
            for i in range(5)
        ]
        _setup_list_mock(mock_session, rows=rows, count=5)
        data = test_client.get("/api/leads/top?limit=100").json()
        assert len(data["leads"]) == 5  # DB returned 5, within limit of 100


# ═══════════════════════════════════════════════════════════════════════════════
#  GET /api/leads/new
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetNewLeadsEmpty:
    """Edge case: no recent leads."""

    def test_returns_200(self, test_client, mock_session):
        _setup_list_mock(mock_session, rows=[], count=0)
        resp = test_client.get("/api/leads/new")
        assert resp.status_code == 200

    def test_leads_is_empty_list(self, test_client, mock_session):
        _setup_list_mock(mock_session, rows=[], count=0)
        data = test_client.get("/api/leads/new").json()
        assert data["leads"] == []

    def test_total_is_zero(self, test_client, mock_session):
        _setup_list_mock(mock_session, rows=[], count=0)
        data = test_client.get("/api/leads/new").json()
        assert data["total"] == 0

    def test_response_has_leads_and_total_keys(self, test_client, mock_session):
        _setup_list_mock(mock_session, rows=[], count=0)
        data = test_client.get("/api/leads/new").json()
        assert "leads" in data
        assert "total" in data


class TestGetNewLeadsWithData:
    """Successful responses with recent lead data."""

    def test_returns_one_lead(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal(absentee_owner=True)
        sc = make_mock_score(last_updated=datetime(2026, 4, 1, tzinfo=timezone.utc))
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        data = test_client.get("/api/leads/new").json()
        assert len(data["leads"]) == 1

    def test_response_shape_matches_lead_response(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal()
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/new").json()["leads"][0]
        required_keys = {"property_id", "county", "parcel_id", "address", "city", "state",
                         "zip", "owner_name", "score", "rank", "signals", "last_updated"}
        assert required_keys.issubset(lead.keys())

    def test_signals_list_in_new_leads(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal(long_term_owner=True)
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=1)
        lead = test_client.get("/api/leads/new").json()["leads"][0]
        assert "long_term_owner" in lead["signals"]

    def test_total_reflects_all_recent(self, test_client, mock_session):
        prop = make_mock_property()
        sig = make_mock_signal()
        sc = make_mock_score()
        _setup_list_mock(mock_session, rows=[(prop, sig, sc)], count=42)
        data = test_client.get("/api/leads/new").json()
        assert data["total"] == 42

    def test_multiple_recent_leads(self, test_client, mock_session):
        rows = [
            (make_mock_property(parcel_id=f"SC-NEW-{i}"), make_mock_signal(), make_mock_score())
            for i in range(4)
        ]
        _setup_list_mock(mock_session, rows=rows, count=4)
        data = test_client.get("/api/leads/new").json()
        assert len(data["leads"]) == 4


class TestGetNewLeadsLimit:
    """Limit parameter validation on /leads/new."""

    def test_default_limit_accepted(self, test_client, mock_session):
        _setup_list_mock(mock_session, rows=[], count=0)
        resp = test_client.get("/api/leads/new")
        assert resp.status_code == 200

    def test_limit_200_accepted(self, test_client, mock_session):
        _setup_list_mock(mock_session, rows=[], count=0)
        resp = test_client.get("/api/leads/new?limit=200")
        assert resp.status_code == 200

    def test_limit_1000_accepted(self, test_client, mock_session):
        _setup_list_mock(mock_session, rows=[], count=0)
        resp = test_client.get("/api/leads/new?limit=1000")
        assert resp.status_code == 200

    def test_limit_1001_rejected(self, test_client, mock_session):
        resp = test_client.get("/api/leads/new?limit=1001")
        assert resp.status_code == 422

    def test_limit_0_rejected(self, test_client, mock_session):
        resp = test_client.get("/api/leads/new?limit=0")
        assert resp.status_code == 422

    def test_limit_negative_rejected(self, test_client, mock_session):
        resp = test_client.get("/api/leads/new?limit=-1")
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
#  GET /api/property/{id}
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetPropertyDetailInvalidInput:
    """Input validation on /property/{id}."""

    def test_invalid_uuid_returns_400(self, test_client, mock_session):
        resp = test_client.get("/api/property/not-a-uuid")
        assert resp.status_code == 400

    def test_invalid_uuid_error_message(self, test_client, mock_session):
        resp = test_client.get("/api/property/not-a-uuid")
        assert "Invalid property ID" in resp.json()["detail"]

    def test_empty_id_segment_returns_404(self, test_client, mock_session):
        # FastAPI routing: /api/property/ with no segment → 404 from router
        resp = test_client.get("/api/property/")
        assert resp.status_code in (404, 405)

    def test_integer_id_returns_400(self, test_client, mock_session):
        resp = test_client.get("/api/property/12345")
        assert resp.status_code == 400

    def test_partial_uuid_returns_400(self, test_client, mock_session):
        resp = test_client.get("/api/property/aaaaaaaa-bbbb-cccc-dddd")
        assert resp.status_code == 400


class TestGetPropertyDetailNotFound:
    """404 responses when property doesn't exist."""

    def test_valid_uuid_not_found_returns_404(self, test_client, mock_session):
        missing_id = uuid.uuid4()
        result = _make_one_result(None)
        mock_session.execute.return_value = result
        resp = test_client.get(f"/api/property/{missing_id}")
        assert resp.status_code == 404

    def test_not_found_error_detail(self, test_client, mock_session):
        missing_id = uuid.uuid4()
        result = _make_one_result(None)
        mock_session.execute.return_value = result
        resp = test_client.get(f"/api/property/{missing_id}")
        assert "not found" in resp.json()["detail"].lower()


class TestGetPropertyDetailSuccess:
    """Successful 200 responses from /property/{id}."""

    def _setup(self, mock_session, prop=None, sig=None, sc=None):
        prop_id = uuid.uuid4()
        p = prop or make_mock_property(prop_id=prop_id)
        s = sig or make_mock_signal(property_id=prop_id)
        sc = sc or make_mock_score(property_id=prop_id)
        result = _make_one_result((p, s, sc))
        mock_session.execute.return_value = result
        return p, s, sc

    def test_returns_200(self, test_client, mock_session):
        prop, _, _ = self._setup(mock_session)
        resp = test_client.get(f"/api/property/{prop.id}")
        assert resp.status_code == 200

    def test_response_has_property_id(self, test_client, mock_session):
        prop, _, _ = self._setup(mock_session)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["property_id"] == str(prop.id)

    def test_response_has_parcel_id(self, test_client, mock_session):
        prop = make_mock_property(parcel_id="SC-DETAIL-001")
        self._setup(mock_session, prop=prop)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["parcel_id"] == "SC-DETAIL-001"

    def test_response_has_county(self, test_client, mock_session):
        prop = make_mock_property(county="jefferson")
        self._setup(mock_session, prop=prop)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["county"] == "jefferson"

    def test_response_has_address(self, test_client, mock_session):
        prop = make_mock_property(address="999 OAK DR")
        self._setup(mock_session, prop=prop)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["address"] == "999 OAK DR"

    def test_response_has_raw_address(self, test_client, mock_session):
        prop = make_mock_property(raw_address="999 Oak Drive")
        self._setup(mock_session, prop=prop)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["raw_address"] == "999 Oak Drive"

    def test_response_has_mailing_address(self, test_client, mock_session):
        prop = make_mock_property(mailing_address="PO BOX 123")
        self._setup(mock_session, prop=prop)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["mailing_address"] == "PO BOX 123"

    def test_response_has_city(self, test_client, mock_session):
        prop = make_mock_property(city="PELHAM")
        self._setup(mock_session, prop=prop)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["city"] == "PELHAM"

    def test_response_has_state(self, test_client, mock_session):
        prop = make_mock_property(state="AL")
        self._setup(mock_session, prop=prop)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["state"] == "AL"

    def test_response_has_zip(self, test_client, mock_session):
        prop = make_mock_property(zip_code="35124")
        self._setup(mock_session, prop=prop)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["zip"] == "35124"

    def test_response_has_owner_name(self, test_client, mock_session):
        prop = make_mock_property(owner_name="BOB JONES")
        self._setup(mock_session, prop=prop)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["owner_name"] == "BOB JONES"

    def test_assessed_value_included(self, test_client, mock_session):
        prop = make_mock_property(assessed_value=225000.0)
        self._setup(mock_session, prop=prop)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["assessed_value"] == 225000.0

    def test_assessed_value_null(self, test_client, mock_session):
        prop = make_mock_property(assessed_value=None)
        self._setup(mock_session, prop=prop)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["assessed_value"] is None

    def test_last_sale_date_null(self, test_client, mock_session):
        prop = make_mock_property(last_sale_date=None)
        self._setup(mock_session, prop=prop)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["last_sale_date"] is None

    def test_owner_name_null(self, test_client, mock_session):
        prop = make_mock_property(owner_name=None)
        self._setup(mock_session, prop=prop)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["owner_name"] is None

    def test_has_created_at(self, test_client, mock_session):
        prop, _, _ = self._setup(mock_session)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert "created_at" in data

    def test_has_updated_at(self, test_client, mock_session):
        prop, _, _ = self._setup(mock_session)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert "updated_at" in data


class TestGetPropertyDetailByParcelId:
    def test_parcel_route_returns_county_scoped_detail(self, test_client, mock_session):
        prop_id = uuid.uuid4()
        prop = make_mock_property(prop_id=prop_id, county="jefferson", parcel_id="JP-001")
        sig = make_mock_signal(property_id=prop_id)
        sc = make_mock_score(property_id=prop_id)
        result = MagicMock()
        result.all.return_value = [(prop, sig, sc)]
        mock_session.execute.return_value = result

        resp = test_client.get("/api/leads/JP-001?county=jefferson")

        assert resp.status_code == 200
        assert resp.json()["county"] == "jefferson"

    def test_parcel_route_requires_county_when_parcel_id_is_ambiguous(self, test_client, mock_session):
        first_id = uuid.uuid4()
        second_id = uuid.uuid4()
        first_row = (
            make_mock_property(prop_id=first_id, county="shelby", parcel_id="DUP-001"),
            make_mock_signal(property_id=first_id),
            make_mock_score(property_id=first_id),
        )
        second_row = (
            make_mock_property(prop_id=second_id, county="jefferson", parcel_id="DUP-001"),
            make_mock_signal(property_id=second_id),
            make_mock_score(property_id=second_id),
        )
        result = MagicMock()
        result.all.return_value = [first_row, second_row]
        mock_session.execute.return_value = result

        resp = test_client.get("/api/leads/DUP-001")

        assert resp.status_code == 409
        assert "Specify county" in resp.json()["detail"]


class TestGetPropertyDetailSignals:
    """Signal boolean map in /property/{id} response."""

    def _setup_with_signal(self, mock_session, **signal_kwargs):
        prop_id = uuid.uuid4()
        prop = make_mock_property(prop_id=prop_id)
        sig = make_mock_signal(property_id=prop_id, **signal_kwargs)
        sc = make_mock_score(property_id=prop_id)
        result = _make_one_result((prop, sig, sc))
        mock_session.execute.return_value = result
        return prop

    def test_signals_key_present(self, test_client, mock_session):
        prop = self._setup_with_signal(mock_session)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert "signals" in data

    def test_signals_has_absentee_owner(self, test_client, mock_session):
        prop = self._setup_with_signal(mock_session, absentee_owner=True)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["signals"]["absentee_owner"] is True

    def test_signals_has_long_term_owner(self, test_client, mock_session):
        prop = self._setup_with_signal(mock_session, long_term_owner=True)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["signals"]["long_term_owner"] is True

    def test_signals_has_tax_delinquent(self, test_client, mock_session):
        prop = self._setup_with_signal(mock_session, tax_delinquent=True)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["signals"]["tax_delinquent"] is True

    def test_signals_has_pre_foreclosure(self, test_client, mock_session):
        prop = self._setup_with_signal(mock_session, pre_foreclosure=True)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["signals"]["pre_foreclosure"] is True

    def test_signals_has_probate(self, test_client, mock_session):
        prop = self._setup_with_signal(mock_session, probate=True)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["signals"]["probate"] is True

    def test_signals_has_eviction(self, test_client, mock_session):
        prop = self._setup_with_signal(mock_session, eviction=True)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["signals"]["eviction"] is True

    def test_signals_has_code_violation(self, test_client, mock_session):
        prop = self._setup_with_signal(mock_session, code_violation=True)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["signals"]["code_violation"] is True

    def test_all_signals_false_when_no_flags(self, test_client, mock_session):
        prop = self._setup_with_signal(mock_session)  # all default False
        data = test_client.get(f"/api/property/{prop.id}").json()
        signals = data["signals"]
        assert all(not v for v in signals.values())

    def test_signals_object_has_all_nine_fields(self, test_client, mock_session):
        prop = self._setup_with_signal(mock_session)
        data = test_client.get(f"/api/property/{prop.id}").json()
        expected_fields = {
            "absentee_owner", "long_term_owner", "out_of_state_owner", "corporate_owner",
            "tax_delinquent", "pre_foreclosure", "probate", "eviction", "code_violation",
        }
        assert expected_fields == set(data["signals"].keys())

    def test_inactive_signal_is_false(self, test_client, mock_session):
        prop = self._setup_with_signal(mock_session, absentee_owner=True)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["signals"]["long_term_owner"] is False


class TestGetPropertyDetailScore:
    """Score detail in /property/{id} response."""

    def _setup_with_score(self, mock_session, **score_kwargs):
        prop_id = uuid.uuid4()
        prop = make_mock_property(prop_id=prop_id)
        sig = make_mock_signal(property_id=prop_id)
        sc = make_mock_score(property_id=prop_id, **score_kwargs)
        result = _make_one_result((prop, sig, sc))
        mock_session.execute.return_value = result
        return prop

    def test_score_key_present(self, test_client, mock_session):
        prop = self._setup_with_score(mock_session)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert "score" in data

    def test_score_value(self, test_client, mock_session):
        prop = self._setup_with_score(mock_session, score=45)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["score"]["score"] == 45

    def test_null_reason_list_is_coerced_to_empty(self, test_client, mock_session):
        prop = make_mock_property(state=None)
        sig = make_mock_signal(property_id=prop.id)
        sc = make_mock_score(property_id=prop.id)
        sc.reason = None
        result = _make_one_result((prop, sig, sc))
        mock_session.execute.return_value = result

        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["state"] == "AL"
        assert data["score"]["reason"] == []

    def test_score_rank(self, test_client, mock_session):
        prop = self._setup_with_score(mock_session, rank="A")
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["score"]["rank"] == "A"

    def test_score_reason_list(self, test_client, mock_session):
        prop = self._setup_with_score(mock_session, reason=["absentee_owner", "long_term_owner"])
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["score"]["reason"] == ["absentee_owner", "long_term_owner"]

    def test_score_reason_empty(self, test_client, mock_session):
        prop = self._setup_with_score(mock_session, score=0, rank="C", reason=[])
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["score"]["reason"] == []

    def test_score_version_preserved(self, test_client, mock_session):
        prop = self._setup_with_score(mock_session, scoring_version="v1")
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["score"]["scoring_version"] == "v1"

    def test_score_last_updated_present(self, test_client, mock_session):
        prop = self._setup_with_score(mock_session)
        data = test_client.get(f"/api/property/{prop.id}").json()
        assert data["score"]["last_updated"] is not None

    def test_score_has_all_required_fields(self, test_client, mock_session):
        prop = self._setup_with_score(mock_session)
        data = test_client.get(f"/api/property/{prop.id}").json()
        required = {"score", "rank", "reason", "scoring_version", "last_updated"}
        assert required.issubset(data["score"].keys())
