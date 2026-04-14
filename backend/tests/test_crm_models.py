"""
Tests for CRM Pydantic models — Sprint 6, Task 16.
app/models/crm.py

Covers:
  PropertyExport
    - All fields round-trip through model_dump
    - Optional fields default to None
    - state defaults to "AL"

  SignalsExport
    - All signal fields default to False
    - All signals can be set to True
    - Bool coercion works correctly

  ScoreExport
    - value, rank, version fields present
    - Rank values A / B / C accepted

  CRMLeadExport
    - Assembles correctly from sub-models
    - tags defaults to empty list
    - exported_at auto-populated as UTC datetime
    - exported_at can be set explicitly
    - model_dump produces correct nested structure
    - tags list preserved

  CRMExportResponse
    - leads list populated correctly
    - total field reflects count
    - exported_at auto-populated
    - Empty leads list valid
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.crm import (
    CRMExportResponse,
    CRMLeadExport,
    PropertyExport,
    ScoreExport,
    SignalsExport,
)


# ── Factories ─────────────────────────────────────────────────────────────────

def make_property_export(**overrides) -> PropertyExport:
    defaults = dict(
        property_id="prop-uuid-001",
        county="shelby",
        parcel_id="SC-0001",
        address="123 MAIN ST",
        raw_address="123 Main Street",
        city="HOOVER",
        state="AL",
        zip="35244",
        owner_name="JANE DOE",
        mailing_address="456 OTHER ST",
        last_sale_date=date(2010, 6, 15),
        assessed_value=175000.0,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return PropertyExport(**defaults)


def make_signals_export(**overrides) -> SignalsExport:
    defaults = dict(
        absentee_owner=True,
        long_term_owner=True,
        out_of_state_owner=False,
        corporate_owner=False,
        tax_delinquent=False,
        pre_foreclosure=False,
        probate=False,
        eviction=False,
        code_violation=False,
    )
    defaults.update(overrides)
    return SignalsExport(**defaults)


def make_score_export(**overrides) -> ScoreExport:
    defaults = dict(value=35, rank="A", mode="broad", version="v2")
    defaults.update(overrides)
    return ScoreExport(**defaults)


def make_crm_lead(**overrides) -> CRMLeadExport:
    defaults = dict(
        property=make_property_export(),
        signals=make_signals_export(),
        score=make_score_export(),
        tags=["absentee_owner", "long_term_owner"],
    )
    defaults.update(overrides)
    return CRMLeadExport(**defaults)


# ── PropertyExport ────────────────────────────────────────────────────────────

class TestPropertyExport:
    def test_all_fields_roundtrip(self):
        prop = make_property_export()
        assert prop.property_id == "prop-uuid-001"
        assert prop.county == "shelby"
        assert prop.parcel_id == "SC-0001"
        assert prop.address == "123 MAIN ST"
        assert prop.raw_address == "123 Main Street"
        assert prop.city == "HOOVER"
        assert prop.state == "AL"
        assert prop.zip == "35244"
        assert prop.owner_name == "JANE DOE"
        assert prop.mailing_address == "456 OTHER ST"
        assert prop.last_sale_date == date(2010, 6, 15)
        assert prop.assessed_value == 175000.0

    def test_optional_fields_default_to_none(self):
        prop = PropertyExport(
            property_id="p1",
            county="shelby",
            parcel_id="X-001",
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert prop.address is None
        assert prop.raw_address is None
        assert prop.city is None
        assert prop.zip is None
        assert prop.owner_name is None
        assert prop.mailing_address is None
        assert prop.last_sale_date is None
        assert prop.assessed_value is None

    def test_state_defaults_to_al(self):
        prop = PropertyExport(
            property_id="p1",
            county="shelby",
            parcel_id="X-001",
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert prop.state == "AL"

    def test_model_dump_includes_all_keys(self):
        prop = make_property_export()
        d = prop.model_dump()
        expected_keys = {
            "property_id", "county", "parcel_id", "address", "raw_address", "city",
            "state", "zip", "owner_name", "mailing_address", "last_sale_date",
            "assessed_value", "created_at", "updated_at",
        }
        assert expected_keys == set(d.keys())

    def test_assessed_value_none(self):
        prop = make_property_export(assessed_value=None)
        assert prop.assessed_value is None

    def test_last_sale_date_none(self):
        prop = make_property_export(last_sale_date=None)
        assert prop.last_sale_date is None


# ── SignalsExport ─────────────────────────────────────────────────────────────

class TestSignalsExport:
    def test_all_default_false(self):
        sig = SignalsExport()
        assert sig.absentee_owner is False
        assert sig.long_term_owner is False
        assert sig.out_of_state_owner is False
        assert sig.corporate_owner is False
        assert sig.tax_delinquent is False
        assert sig.pre_foreclosure is False
        assert sig.probate is False
        assert sig.eviction is False
        assert sig.code_violation is False

    def test_all_signals_true(self):
        sig = SignalsExport(
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
        assert all([
            sig.absentee_owner, sig.long_term_owner, sig.out_of_state_owner, sig.corporate_owner, sig.tax_delinquent,
            sig.pre_foreclosure, sig.probate, sig.eviction, sig.code_violation,
        ])

    def test_partial_signals(self):
        sig = SignalsExport(absentee_owner=True, long_term_owner=True)
        assert sig.absentee_owner is True
        assert sig.long_term_owner is True
        assert sig.out_of_state_owner is False
        assert sig.corporate_owner is False
        assert sig.tax_delinquent is False

    def test_model_dump_has_seven_fields(self):
        sig = SignalsExport()
        d = sig.model_dump()
        assert len(d) == 9

    def test_expected_signal_fields_present(self):
        sig = SignalsExport()
        d = sig.model_dump()
        expected = {
            "absentee_owner", "long_term_owner", "out_of_state_owner", "corporate_owner", "tax_delinquent",
            "pre_foreclosure", "probate", "eviction", "code_violation",
        }
        assert set(d.keys()) == expected


# ── ScoreExport ───────────────────────────────────────────────────────────────

class TestScoreExport:
    def test_basic_fields(self):
        sc = ScoreExport(value=35, rank="A", version="v2")
        assert sc.value == 35
        assert sc.rank == "A"
        assert sc.mode == "broad"
        assert sc.version == "v2"

    def test_rank_b(self):
        sc = ScoreExport(value=20, rank="B", version="v2")
        assert sc.rank == "B"

    def test_rank_c(self):
        sc = ScoreExport(value=10, rank="C", version="v2")
        assert sc.rank == "C"

    def test_score_zero(self):
        sc = ScoreExport(value=0, rank="C", version="v2")
        assert sc.value == 0

    def test_model_dump_keys(self):
        sc = ScoreExport(value=25, rank="A", version="v2")
        d = sc.model_dump()
        assert set(d.keys()) == {"value", "rank", "mode", "version"}

    def test_version_string_preserved(self):
        sc = ScoreExport(value=30, rank="A", version="v2")
        assert sc.version == "v2"


# ── CRMLeadExport ─────────────────────────────────────────────────────────────

class TestCRMLeadExport:
    def test_assembles_from_sub_models(self):
        lead = make_crm_lead()
        assert lead.property.county == "shelby"
        assert lead.property.parcel_id == "SC-0001"
        assert lead.signals.absentee_owner is True
        assert lead.score.value == 35
        assert lead.score.rank == "A"
        assert "absentee_owner" in lead.tags

    def test_tags_defaults_to_empty_list(self):
        lead = CRMLeadExport(
            property=make_property_export(),
            signals=make_signals_export(),
            score=make_score_export(),
        )
        assert lead.tags == []

    def test_exported_at_is_set_automatically(self):
        lead = make_crm_lead()
        assert isinstance(lead.exported_at, datetime)
        assert lead.exported_at.tzinfo is not None

    def test_exported_at_can_be_overridden(self):
        ts = datetime(2026, 4, 3, 12, 0, 0, tzinfo=timezone.utc)
        lead = make_crm_lead(exported_at=ts)
        assert lead.exported_at == ts

    def test_model_dump_json_nested_structure(self):
        lead = make_crm_lead()
        d = lead.model_dump(mode="json")
        assert "property" in d
        assert "signals" in d
        assert "score" in d
        assert "tags" in d
        assert "exported_at" in d
        # Nested keys
        assert "county" in d["property"]
        assert "parcel_id" in d["property"]
        assert "absentee_owner" in d["signals"]
        assert "value" in d["score"]

    def test_tags_list_preserved(self):
        tags = ["absentee_owner", "long_term_owner", "tax_delinquent"]
        lead = make_crm_lead(tags=tags)
        assert lead.tags == tags

    def test_empty_tags_list(self):
        lead = make_crm_lead(tags=[])
        assert lead.tags == []

    def test_score_value_zero(self):
        lead = make_crm_lead(score=ScoreExport(value=0, rank="C", version="v2"))
        assert lead.score.value == 0

    def test_property_all_none_optionals(self):
        prop = PropertyExport(
            property_id="p99",
            county="shelby",
            parcel_id="NULL-001",
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        lead = CRMLeadExport(
            property=prop,
            signals=SignalsExport(),
            score=ScoreExport(value=0, rank="C", version="v2"),
        )
        assert lead.property.address is None
        assert lead.property.city is None


# ── CRMExportResponse ─────────────────────────────────────────────────────────

class TestCRMExportResponse:
    def test_basic_structure(self):
        lead = make_crm_lead()
        resp = CRMExportResponse(leads=[lead], total=1)
        assert len(resp.leads) == 1
        assert resp.total == 1

    def test_empty_leads_list_valid(self):
        resp = CRMExportResponse(leads=[], total=0)
        assert resp.leads == []
        assert resp.total == 0

    def test_exported_at_auto_populated(self):
        resp = CRMExportResponse(leads=[], total=0)
        assert isinstance(resp.exported_at, datetime)
        assert resp.exported_at.tzinfo is not None

    def test_total_independent_of_leads_length(self):
        # total can be > len(leads) when a limit is applied
        lead = make_crm_lead()
        resp = CRMExportResponse(leads=[lead], total=500)
        assert resp.total == 500
        assert len(resp.leads) == 1

    def test_multiple_leads(self):
        leads = [make_crm_lead() for _ in range(5)]
        resp = CRMExportResponse(leads=leads, total=5)
        assert len(resp.leads) == 5

    def test_model_dump_keys(self):
        resp = CRMExportResponse(leads=[], total=0)
        d = resp.model_dump()
        assert set(d.keys()) == {"leads", "total", "exported_at"}

    def test_exported_at_override(self):
        ts = datetime(2026, 4, 3, tzinfo=timezone.utc)
        resp = CRMExportResponse(leads=[], total=0, exported_at=ts)
        assert resp.exported_at == ts
