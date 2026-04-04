"""
RSE CRM Export Models — Sprint 6, Task 16
app/models/crm.py

Pydantic models defining the standardized CRM export payload format.
These models are used by both the export endpoints and the WebhookService.

Models:
  PropertyExport      — all property fields, suitable for CRM ingestion
  SignalsExport       — full boolean signal map
  ScoreExport         — score value, rank letter, and scoring version
  CRMLeadExport       — full CRM record: property + signals + score + tags + timestamp
  CRMExportResponse   — paginated list of CRM records with export metadata
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Property sub-record ───────────────────────────────────────────────────────

class PropertyExport(BaseModel):
    """All property fields in a CRM-consumable flat structure."""
    model_config = ConfigDict(from_attributes=True)

    property_id: str
    parcel_id: str
    address: Optional[str] = None
    raw_address: Optional[str] = None
    city: Optional[str] = None
    state: str = "AL"
    zip: Optional[str] = None
    owner_name: Optional[str] = None
    mailing_address: Optional[str] = None
    last_sale_date: Optional[date] = None
    assessed_value: Optional[float] = None
    created_at: datetime
    updated_at: datetime


# ── Signals sub-record ────────────────────────────────────────────────────────

class SignalsExport(BaseModel):
    """
    Complete boolean signal map.

    Every signal field is included regardless of its value so CRM consumers
    get a deterministic schema on every record.
    """
    model_config = ConfigDict(from_attributes=True)

    absentee_owner: bool = False
    long_term_owner: bool = False
    tax_delinquent: bool = False
    pre_foreclosure: bool = False
    probate: bool = False
    eviction: bool = False
    code_violation: bool = False


# ── Score sub-record ──────────────────────────────────────────────────────────

class ScoreExport(BaseModel):
    """
    Scoring summary for CRM consumption.

    Uses `value` (not `score`) to match the CRM contract spec so downstream
    systems can map it unambiguously. `version` tracks which weight table
    produced the score.
    """
    model_config = ConfigDict(from_attributes=True)

    value: int
    rank: str       # "A" | "B" | "C"
    version: str    # e.g. "v1"


# ── Full CRM lead record ──────────────────────────────────────────────────────

class CRMLeadExport(BaseModel):
    """
    Canonical CRM export record for a single property.

    Shape:
      {
        "property": { ...all property fields },
        "signals":  { ...all signal booleans },
        "score":    { "value": 35, "rank": "A", "version": "v1" },
        "tags":     ["absentee_owner", "long_term_owner"],
        "exported_at": "2026-04-03T..."
      }

    `tags` is the subset of active signal names — mirrors `scores.reason` —
    so CRM consumers can filter/segment without parsing the signals map.
    `exported_at` is the UTC timestamp this record was serialised, not the
    score's last_updated. Set by the endpoint at response time.
    """
    property: PropertyExport
    signals: SignalsExport
    score: ScoreExport
    tags: list[str] = Field(default_factory=list)
    exported_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


# ── Collection response ───────────────────────────────────────────────────────

class CRMExportResponse(BaseModel):
    """
    Paginated CRM export — returned by GET /api/leads/export.

    `total` is the count of matching records before the `limit` is applied
    (mirrors the pattern used in LeadsListResponse).
    `exported_at` is the UTC timestamp of this export batch.
    """
    leads: list[CRMLeadExport]
    total: int
    exported_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
