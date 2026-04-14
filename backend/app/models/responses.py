"""
RSE Pydantic Response Models — Sprint 5, Tasks 11 & 12
app/models/responses.py

These models define the exact JSON shapes returned by the API layer.
Pydantic validates outbound data so callers get consistent, typed responses.

Models:
  LeadResponse           — single lead row (property + active signals + score)
  LeadsListResponse      — paginated leads list with total count
  SignalDetail           — full signal boolean map (used in property detail)
  ScoreDetail            — score + rank + reason tags + version
  PropertyDetailResponse — full property detail: all fields + signals + score
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ── Lead (summary) ────────────────────────────────────────────────────────────

class LeadResponse(BaseModel):
    """
    Summary view of a single lead — suitable for the leads table.

    `signals` is a list of active signal names (e.g. ["absentee_owner",
    "long_term_owner"]). Only True signals are included — False ones are
    omitted to keep the response compact.
    """
    model_config = ConfigDict(from_attributes=True)

    property_id: str
    county: str = "shelby"
    parcel_id: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: str = "AL"
    zip: Optional[str] = None
    owner_name: Optional[str] = None
    assessed_value: Optional[float] = None
    score: int
    rank: str                    # "A" | "B" | "C"
    scoring_mode: str = "broad"
    signals: list[str]           # active signal names only
    signal_count: int = 0
    last_updated: datetime


class LeadsListResponse(BaseModel):
    """Paginated list of leads plus the total matching count (before limit)."""
    leads: list[LeadResponse]
    total: int
    limit: int = 50
    offset: int = 0


# ── Signal detail (boolean map) ───────────────────────────────────────────────

class SignalDetail(BaseModel):
    """
    Full boolean map of every signal field.
    Used in PropertyDetailResponse so callers can see exactly which signals
    are active vs. inactive.
    """
    model_config = ConfigDict(from_attributes=True)

    absentee_owner: bool = False
    long_term_owner: bool = False
    out_of_state_owner: bool = False
    corporate_owner: bool = False
    tax_delinquent: bool = False
    pre_foreclosure: bool = False
    probate: bool = False
    eviction: bool = False
    code_violation: bool = False


# ── Score detail ──────────────────────────────────────────────────────────────

class ScoreDetail(BaseModel):
    """Full score record including reason tags and the weight version used."""
    model_config = ConfigDict(from_attributes=True)

    score: int
    rank: str                    # "A" | "B" | "C"
    reason: list[str]            # active signal tags that contributed
    scoring_mode: str = "broad"
    scoring_version: str
    last_updated: datetime


# ── Property detail (full) ────────────────────────────────────────────────────

class PropertyDetailResponse(BaseModel):
    """
    Full property detail: all property fields + complete signal booleans
    + full score record.

    Returned by GET /property/{id}.
    """
    model_config = ConfigDict(from_attributes=True)

    property_id: str
    county: str = "shelby"
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
    signals: SignalDetail
    score: ScoreDetail
    created_at: datetime
    updated_at: datetime
