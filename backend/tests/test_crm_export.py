"""
Tests for CRM Export API endpoints — Sprint 6, Task 16.
app/api/export.py

Strategy:
  - No live database. DB session mocked via conftest fixtures (mock_session /
    test_client pattern from existing test suite).
  - session.execute() configured with side_effect lists for data + count queries.

Covers:
  GET /api/leads/export
    - Empty DB → {"leads": [], "total": 0, "exported_at": ...}
    - Returns CRMExportResponse shape with nested property/signals/score/tags
    - Tags list matches score.reason
    - min_score filter accepted
    - rank filter accepted (A, B, C)
    - rank filter — invalid value → 422
    - limit default (100) accepted
    - limit max 500 accepted
    - limit > 500 → 422
    - limit < 1 → 422
    - format=json accepted
    - format=csv → 400
    - Multiple leads returned
    - total > len(leads) scenario (pagination)
    - score.value field present (not "score")
    - score.version field present (not "scoring_version")
    - exported_at field present at top level and per-lead
    - property sub-object has all expected keys
    - signals sub-object has all seven boolean fields
    - All optional property fields null when None
    - tags empty list when score.reason is empty
    - assessed_value float when present

  GET /api/leads/export/{id}
    - Valid UUID + found → CRMLeadExport shape
    - Invalid UUID → 400
    - Valid UUID, not found → 404
    - Returned CRMLeadExport has correct nested structure
    - tags from score.reason
    - score.value (not score.score)
    - score.version (not scoring_version)
    - exported_at present
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_mock_property, make_mock_score, make_mock_signal

# ── Expected keys ─────────────────────────────────────────────────────────────

_PROPERTY_KEYS = {
    "property_id", "county", "parcel_id", "address", "raw_address", "city", "state", "zip",
    "owner_name", "mailing_address", "last_sale_date", "assessed_value",
    "created_at", "updated_at",
}

_SIGNALS_KEYS = {
    "absentee_owner", "long_term_owner", "out_of_state_owner", "corporate_owner", "tax_delinquent",
    "pre_foreclosure", "probate", "eviction", "code_violation",
}

_SCORE_KEYS = {"value", "rank", "version"}

_LEAD_KEYS = {"property", "signals", "score", "tags", "exported_at"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_row(prop=None, signal=None, score=None):
    """Build a mock SQLAlchemy result row (3-tuple)."""
    return (
        prop or make_mock_property(),
        signal or make_mock_signal(absentee_owner=True, long_term_owner=True),
        score or make_mock_score(score=35, rank="A", reason=["absentee_owner", "long_term_owner"]),
    )


def _mock_execute_pair(session: AsyncMock, rows: list, total: int) -> None:
    """Configure session.execute() side_effect for data + count queries."""
    data_result = MagicMock()
    data_result.all.return_value = rows

    count_result = MagicMock()
    count_result.scalar.return_value = total

    session.execute = AsyncMock(side_effect=[data_result, count_result])


# ── GET /api/leads/export — collection ───────────────────────────────────────

class TestExportLeads:

    def test_empty_db_returns_valid_response(self, test_client: TestClient, mock_session: AsyncMock):
        _mock_execute_pair(mock_session, rows=[], total=0)
        resp = test_client.get("/api/leads/export")
        assert resp.status_code == 200
        body = resp.json()
        assert body["leads"] == []
        assert body["total"] == 0
        assert "exported_at" in body

    def test_response_has_crm_export_response_shape(self, test_client: TestClient, mock_session: AsyncMock):
        _mock_execute_pair(mock_session, rows=[_mock_row()], total=1)
        body = test_client.get("/api/leads/export").json()
        assert "leads" in body
        assert "total" in body
        assert "exported_at" in body

    def test_lead_has_correct_top_level_keys(self, test_client: TestClient, mock_session: AsyncMock):
        _mock_execute_pair(mock_session, rows=[_mock_row()], total=1)
        lead = test_client.get("/api/leads/export").json()["leads"][0]
        assert set(lead.keys()) == _LEAD_KEYS

    def test_property_sub_object_keys(self, test_client: TestClient, mock_session: AsyncMock):
        _mock_execute_pair(mock_session, rows=[_mock_row()], total=1)
        lead = test_client.get("/api/leads/export").json()["leads"][0]
        assert set(lead["property"].keys()) == _PROPERTY_KEYS

    def test_property_county_value_present(self, test_client: TestClient, mock_session: AsyncMock):
        prop = make_mock_property(county="jefferson")
        _mock_execute_pair(mock_session, rows=[_mock_row(prop=prop)], total=1)
        lead = test_client.get("/api/leads/export").json()["leads"][0]
        assert lead["property"]["county"] == "jefferson"

    def test_signals_sub_object_keys(self, test_client: TestClient, mock_session: AsyncMock):
        _mock_execute_pair(mock_session, rows=[_mock_row()], total=1)
        lead = test_client.get("/api/leads/export").json()["leads"][0]
        assert set(lead["signals"].keys()) == _SIGNALS_KEYS

    def test_score_sub_object_keys(self, test_client: TestClient, mock_session: AsyncMock):
        _mock_execute_pair(mock_session, rows=[_mock_row()], total=1)
        lead = test_client.get("/api/leads/export").json()["leads"][0]
        assert set(lead["score"].keys()) == _SCORE_KEYS

    def test_score_uses_value_not_score_key(self, test_client: TestClient, mock_session: AsyncMock):
        _mock_execute_pair(mock_session, rows=[_mock_row()], total=1)
        lead = test_client.get("/api/leads/export").json()["leads"][0]
        assert "value" in lead["score"]
        assert "score" not in lead["score"]

    def test_score_uses_version_not_scoring_version(self, test_client: TestClient, mock_session: AsyncMock):
        _mock_execute_pair(mock_session, rows=[_mock_row()], total=1)
        lead = test_client.get("/api/leads/export").json()["leads"][0]
        assert "version" in lead["score"]
        assert "scoring_version" not in lead["score"]

    def test_score_value_correct(self, test_client: TestClient, mock_session: AsyncMock):
        score = make_mock_score(score=42, rank="A", reason=["absentee_owner"])
        _mock_execute_pair(mock_session, rows=[_mock_row(score=score)], total=1)
        lead = test_client.get("/api/leads/export").json()["leads"][0]
        assert lead["score"]["value"] == 42

    def test_tags_matches_score_reason(self, test_client: TestClient, mock_session: AsyncMock):
        score = make_mock_score(reason=["absentee_owner", "long_term_owner"])
        _mock_execute_pair(mock_session, rows=[_mock_row(score=score)], total=1)
        lead = test_client.get("/api/leads/export").json()["leads"][0]
        assert lead["tags"] == ["absentee_owner", "long_term_owner"]

    def test_tags_empty_when_reason_empty(self, test_client: TestClient, mock_session: AsyncMock):
        score = make_mock_score(reason=[])
        _mock_execute_pair(mock_session, rows=[_mock_row(score=score)], total=1)
        lead = test_client.get("/api/leads/export").json()["leads"][0]
        assert lead["tags"] == []

    def test_signals_absentee_owner_true(self, test_client: TestClient, mock_session: AsyncMock):
        signal = make_mock_signal(absentee_owner=True)
        _mock_execute_pair(mock_session, rows=[_mock_row(signal=signal)], total=1)
        lead = test_client.get("/api/leads/export").json()["leads"][0]
        assert lead["signals"]["absentee_owner"] is True

    def test_signals_all_false(self, test_client: TestClient, mock_session: AsyncMock):
        signal = make_mock_signal()
        _mock_execute_pair(mock_session, rows=[_mock_row(signal=signal)], total=1)
        lead = test_client.get("/api/leads/export").json()["leads"][0]
        for k in _SIGNALS_KEYS:
            assert lead["signals"][k] is False

    def test_exported_at_per_lead_present(self, test_client: TestClient, mock_session: AsyncMock):
        _mock_execute_pair(mock_session, rows=[_mock_row()], total=1)
        lead = test_client.get("/api/leads/export").json()["leads"][0]
        assert "exported_at" in lead
        # Should be an ISO 8601 string — normalize Z suffix for Python 3.10 compat
        datetime.fromisoformat(lead["exported_at"].replace("Z", "+00:00"))

    def test_total_independent_of_lead_count(self, test_client: TestClient, mock_session: AsyncMock):
        _mock_execute_pair(mock_session, rows=[_mock_row()], total=999)
        body = test_client.get("/api/leads/export").json()
        assert body["total"] == 999
        assert len(body["leads"]) == 1

    def test_multiple_leads_returned(self, test_client: TestClient, mock_session: AsyncMock):
        rows = [_mock_row() for _ in range(3)]
        _mock_execute_pair(mock_session, rows=rows, total=3)
        body = test_client.get("/api/leads/export").json()
        assert len(body["leads"]) == 3

    def test_min_score_query_param_accepted(self, test_client: TestClient, mock_session: AsyncMock):
        _mock_execute_pair(mock_session, rows=[_mock_row()], total=1)
        resp = test_client.get("/api/leads/export?min_score=25")
        assert resp.status_code == 200

    def test_rank_a_filter_accepted(self, test_client: TestClient, mock_session: AsyncMock):
        _mock_execute_pair(mock_session, rows=[_mock_row()], total=1)
        resp = test_client.get("/api/leads/export?rank=A")
        assert resp.status_code == 200

    def test_rank_b_filter_accepted(self, test_client: TestClient, mock_session: AsyncMock):
        _mock_execute_pair(mock_session, rows=[], total=0)
        resp = test_client.get("/api/leads/export?rank=B")
        assert resp.status_code == 200

    def test_rank_c_filter_accepted(self, test_client: TestClient, mock_session: AsyncMock):
        _mock_execute_pair(mock_session, rows=[], total=0)
        resp = test_client.get("/api/leads/export?rank=C")
        assert resp.status_code == 200

    def test_invalid_rank_returns_422(self, test_client: TestClient, mock_session: AsyncMock):
        resp = test_client.get("/api/leads/export?rank=Z")
        assert resp.status_code == 422

    def test_format_json_accepted(self, test_client: TestClient, mock_session: AsyncMock):
        _mock_execute_pair(mock_session, rows=[], total=0)
        resp = test_client.get("/api/leads/export?format=json")
        assert resp.status_code == 200

    def test_format_csv_returns_400(self, test_client: TestClient, mock_session: AsyncMock):
        resp = test_client.get("/api/leads/export?format=csv")
        assert resp.status_code == 400

    def test_limit_default_accepted(self, test_client: TestClient, mock_session: AsyncMock):
        _mock_execute_pair(mock_session, rows=[], total=0)
        resp = test_client.get("/api/leads/export")
        assert resp.status_code == 200

    def test_limit_500_accepted(self, test_client: TestClient, mock_session: AsyncMock):
        _mock_execute_pair(mock_session, rows=[], total=0)
        resp = test_client.get("/api/leads/export?limit=500")
        assert resp.status_code == 200

    def test_limit_above_500_returns_422(self, test_client: TestClient, mock_session: AsyncMock):
        resp = test_client.get("/api/leads/export?limit=501")
        assert resp.status_code == 422

    def test_limit_zero_returns_422(self, test_client: TestClient, mock_session: AsyncMock):
        resp = test_client.get("/api/leads/export?limit=0")
        assert resp.status_code == 422

    def test_limit_negative_returns_422(self, test_client: TestClient, mock_session: AsyncMock):
        resp = test_client.get("/api/leads/export?limit=-1")
        assert resp.status_code == 422

    def test_min_score_negative_returns_422(self, test_client: TestClient, mock_session: AsyncMock):
        resp = test_client.get("/api/leads/export?min_score=-5")
        assert resp.status_code == 422

    def test_assessed_value_float_in_response(self, test_client: TestClient, mock_session: AsyncMock):
        prop = make_mock_property(assessed_value=250000.0)
        _mock_execute_pair(mock_session, rows=[_mock_row(prop=prop)], total=1)
        lead = test_client.get("/api/leads/export").json()["leads"][0]
        assert lead["property"]["assessed_value"] == 250000.0

    def test_assessed_value_null_when_none(self, test_client: TestClient, mock_session: AsyncMock):
        prop = make_mock_property(assessed_value=None)
        _mock_execute_pair(mock_session, rows=[_mock_row(prop=prop)], total=1)
        lead = test_client.get("/api/leads/export").json()["leads"][0]
        assert lead["property"]["assessed_value"] is None

    def test_owner_name_null_when_none(self, test_client: TestClient, mock_session: AsyncMock):
        prop = make_mock_property(owner_name=None)
        _mock_execute_pair(mock_session, rows=[_mock_row(prop=prop)], total=1)
        lead = test_client.get("/api/leads/export").json()["leads"][0]
        assert lead["property"]["owner_name"] is None

    def test_city_null_when_none(self, test_client: TestClient, mock_session: AsyncMock):
        prop = make_mock_property(city=None)
        _mock_execute_pair(mock_session, rows=[_mock_row(prop=prop)], total=1)
        lead = test_client.get("/api/leads/export").json()["leads"][0]
        assert lead["property"]["city"] is None

    def test_rank_a_present_in_score(self, test_client: TestClient, mock_session: AsyncMock):
        score = make_mock_score(score=35, rank="A")
        _mock_execute_pair(mock_session, rows=[_mock_row(score=score)], total=1)
        lead = test_client.get("/api/leads/export").json()["leads"][0]
        assert lead["score"]["rank"] == "A"

    def test_rank_b_present_in_score(self, test_client: TestClient, mock_session: AsyncMock):
        score = make_mock_score(score=20, rank="B")
        _mock_execute_pair(mock_session, rows=[_mock_row(score=score)], total=1)
        lead = test_client.get("/api/leads/export").json()["leads"][0]
        assert lead["score"]["rank"] == "B"


# ── GET /api/leads/export/{id} — single record ───────────────────────────────

class TestExportLeadById:

    def _configure_single(self, session: AsyncMock, row=None, found: bool = True):
        result = MagicMock()
        result.one_or_none.return_value = row if found else None
        session.execute = AsyncMock(return_value=result)

    def test_valid_uuid_returns_crm_lead(self, test_client: TestClient, mock_session: AsyncMock):
        prop_id = uuid.uuid4()
        prop = make_mock_property(prop_id=prop_id)
        signal = make_mock_signal(absentee_owner=True)
        score = make_mock_score(score=30, rank="A", reason=["absentee_owner"])
        self._configure_single(mock_session, row=(prop, signal, score))
        resp = test_client.get(f"/api/leads/export/{prop_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == _LEAD_KEYS

    def test_invalid_uuid_returns_400(self, test_client: TestClient, mock_session: AsyncMock):
        resp = test_client.get("/api/leads/export/not-a-uuid")
        assert resp.status_code == 400

    def test_not_found_returns_404(self, test_client: TestClient, mock_session: AsyncMock):
        self._configure_single(mock_session, found=False)
        resp = test_client.get(f"/api/leads/export/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_score_value_field_not_score(self, test_client: TestClient, mock_session: AsyncMock):
        score = make_mock_score(score=28)
        self._configure_single(mock_session, row=_mock_row(score=score))
        body = test_client.get(f"/api/leads/export/{uuid.uuid4()}").json()
        assert "value" in body["score"]
        assert "score" not in body["score"]

    def test_score_version_field(self, test_client: TestClient, mock_session: AsyncMock):
        self._configure_single(mock_session, row=_mock_row())
        body = test_client.get(f"/api/leads/export/{uuid.uuid4()}").json()
        assert "version" in body["score"]

    def test_tags_from_reason(self, test_client: TestClient, mock_session: AsyncMock):
        score = make_mock_score(reason=["absentee_owner"])
        self._configure_single(mock_session, row=_mock_row(score=score))
        body = test_client.get(f"/api/leads/export/{uuid.uuid4()}").json()
        assert body["tags"] == ["absentee_owner"]

    def test_exported_at_present(self, test_client: TestClient, mock_session: AsyncMock):
        self._configure_single(mock_session, row=_mock_row())
        body = test_client.get(f"/api/leads/export/{uuid.uuid4()}").json()
        assert "exported_at" in body
        datetime.fromisoformat(body["exported_at"].replace("Z", "+00:00"))

    def test_property_sub_keys(self, test_client: TestClient, mock_session: AsyncMock):
        self._configure_single(mock_session, row=_mock_row())
        body = test_client.get(f"/api/leads/export/{uuid.uuid4()}").json()
        assert set(body["property"].keys()) == _PROPERTY_KEYS

    def test_signals_sub_keys(self, test_client: TestClient, mock_session: AsyncMock):
        self._configure_single(mock_session, row=_mock_row())
        body = test_client.get(f"/api/leads/export/{uuid.uuid4()}").json()
        assert set(body["signals"].keys()) == _SIGNALS_KEYS

    def test_score_sub_keys(self, test_client: TestClient, mock_session: AsyncMock):
        self._configure_single(mock_session, row=_mock_row())
        body = test_client.get(f"/api/leads/export/{uuid.uuid4()}").json()
        assert set(body["score"].keys()) == _SCORE_KEYS
