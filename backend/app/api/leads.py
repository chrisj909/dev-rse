"""
RSE Lead Endpoints â Sprint 5, Tasks 11 & 12
app/api/leads.py

Routes:
  GET /api/leads/top          â top-scored properties (filters + limit)
  GET /api/leads/new          â recently updated leads (last 7 days)
  GET /api/property/{id}      â full property detail with signals + score

All routes return Pydantic-validated responses defined in app/models/responses.py.
DB access uses the async session dependency from app/db/session.py.

Filtering (Task 12) on /leads/top:
  min_score       int  â minimum score threshold (inclusive)
  absentee_owner  bool â restrict to absentee-owned properties
  long_term_owner bool â restrict to long-term owner properties
  city            str  â city name match (case-insensitive)
  limit           int  â result cap (default 50, max 200)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.property import Property
from app.models.responses import (
    LeadResponse,
    LeadsListResponse,
    PropertyDetailResponse,
    ScoreDetail,
    SignalDetail,
)
from app.models.score import Score
from app.models.signal import Signal

router = APIRouter(tags=["leads"])

# Ordered list of all signal column names on the Signal ORM model.
# Order determines the canonical order of active signal names in the response.
_SIGNAL_FIELDS: list[str] = [
    "absentee_owner",
    "long_term_owner",
    "tax_delinquent",
    "pre_foreclosure",
    "probate",
    "eviction",
    "code_violation",
]


# ââ Helpers âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def _active_signals(signal: Signal) -> list[str]:
    """
    Return only the signal names that are True on this Signal row.

    Order matches _SIGNAL_FIELDS â deterministic across calls.
    """
    return [field for field in _SIGNAL_FIELDS if getattr(signal, field, False)]


def _build_lead(prop: Property, signal: Signal, score: Score) -> LeadResponse:
    """Assemble a LeadResponse from ORM rows."""
    active_signals = _active_signals(signal)
    return LeadResponse(
        property_id=str(prop.id),
        parcel_id=prop.parcel_id,
        address=prop.address,
        city=prop.city,
        state=prop.state,
        zip=prop.zip,
        owner_name=prop.owner_name,
        score=score.score,
        rank=score.rank,
        signals=active_signals,
        signal_count=len(active_signals),
        last_updated=score.last_updated,
    )


# ââ GET /api/leads/top ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

@router.get("/leads", response_model=LeadsListResponse)
@router.get("/leads/top", response_model=LeadsListResponse)
async def get_top_leads(
    min_score: Optional[int] = Query(default=None, ge=0, description="Minimum score threshold (inclusive)."),
    absentee_owner: Optional[bool] = Query(default=None, description="Filter to absentee-owned properties only."),
    long_term_owner: Optional[bool] = Query(default=None, description="Filter to long-term owner properties."),
    city: Optional[str] = Query(default=None, description="Filter by city name (case-insensitive)."),
    limit: int = Query(default=50, ge=1, le=200, description="Max results to return (default 50, max 200)."),
    session: AsyncSession = Depends(get_db),
) -> LeadsListResponse:
    """
    Return the top-scored properties, sorted by score descending.

    Requires that signal and score rows exist for each property (inner join).
    Properties without scores are excluded â run the scoring job first.

    Returns:
        LeadsListResponse with matched leads (up to `limit`) and the
        total count of matching records before the limit is applied.
    """
    conditions = _build_filter_conditions(min_score, absentee_owner, long_term_owner, city)

    # Data query â ordered by score DESC
    data_stmt = (
        select(Property, Signal, Score)
        .join(Signal, Signal.property_id == Property.id)
        .join(Score, Score.property_id == Property.id)
        .order_by(Score.score.desc())
        .limit(limit)
    )
    if conditions:
        data_stmt = data_stmt.where(*conditions)

    data_result = await session.execute(data_stmt)
    rows = data_result.all()

    # Count query â total matching before limit
    count_stmt = (
        select(func.count(Property.id))
        .join(Signal, Signal.property_id == Property.id)
        .join(Score, Score.property_id == Property.id)
    )
    if conditions:
        count_stmt = count_stmt.where(*conditions)

    count_result = await session.execute(count_stmt)
    total: int = count_result.scalar() or 0

    leads = [_build_lead(prop, signal, score) for prop, signal, score in rows]
    return LeadsListResponse(leads=leads, total=total)


# ââ GET /api/leads/new ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

@router.get("/leads/new", response_model=LeadsListResponse)
async def get_new_leads(
    limit: int = Query(default=50, ge=1, le=200, description="Max results (default 50, max 200)."),
    session: AsyncSession = Depends(get_db),
) -> LeadsListResponse:
    """
    Return recently updated leads â those scored or re-scored in the last 7 days.

    Ordered by last_updated descending (most recent first).

    Returns:
        LeadsListResponse with matched leads (up to `limit`) and total count.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)

    data_stmt = (
        select(Property, Signal, Score)
        .join(Signal, Signal.property_id == Property.id)
        .join(Score, Score.property_id == Property.id)
        .where(Score.last_updated >= cutoff)
        .order_by(Score.last_updated.desc())
        .limit(limit)
    )

    data_result = await session.execute(data_stmt)
    rows = data_result.all()

    count_stmt = (
        select(func.count(Property.id))
        .join(Signal, Signal.property_id == Property.id)
        .join(Score, Score.property_id == Property.id)
        .where(Score.last_updated >= cutoff)
    )
    count_result = await session.execute(count_stmt)
    total: int = count_result.scalar() or 0

    leads = [_build_lead(prop, signal, score) for prop, signal, score in rows]
    return LeadsListResponse(leads=leads, total=total)


# ââ GET /api/property/{property_id} ââââââââââââââââââââââââââââââââââââââââââ

@router.get("/property/{property_id}", response_model=PropertyDetailResponse)
async def get_property_detail(
    property_id: str,
    session: AsyncSession = Depends(get_db),
) -> PropertyDetailResponse:
    """
    Return full detail for a single property.

    Includes all property fields, the complete signal boolean map, and the
    full score record (score, rank, reason tags, scoring version).

    Raises:
        400 Bad Request â if `property_id` is not a valid UUID.
        404 Not Found   â if the property doesn't exist, or lacks signal/score data.
    """
    try:
        prop_uuid = uuid.UUID(property_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid property ID â must be a valid UUID.")

    row = await _fetch_property_detail_row(session, Property.id == prop_uuid)
    return _build_property_detail_response(row)


@router.get("/leads/{parcel_id}", response_model=PropertyDetailResponse)
async def get_property_detail_by_parcel_id(
    parcel_id: str,
    session: AsyncSession = Depends(get_db),
) -> PropertyDetailResponse:
    """Return full property detail using the public parcel_id route key."""
    row = await _fetch_property_detail_row(session, Property.parcel_id == parcel_id)
    return _build_property_detail_response(row)


# ââ Internal helpers ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def _build_filter_conditions(
    min_score: Optional[int],
    absentee_owner: Optional[bool],
    long_term_owner: Optional[bool],
    city: Optional[str],
) -> list:
    """
    Build a list of SQLAlchemy WHERE clause conditions from filter params.

    Each condition is appended only when the corresponding param is not None.
    Pass the returned list directly to `.where(*conditions)`.
    """
    conditions = []
    if min_score is not None:
        conditions.append(Score.score >= min_score)
    if absentee_owner is not None:
        conditions.append(Signal.absentee_owner == absentee_owner)
    if long_term_owner is not None:
        conditions.append(Signal.long_term_owner == long_term_owner)
    if city is not None:
        conditions.append(Property.city.ilike(city))
    return conditions


async def _fetch_property_detail_row(session: AsyncSession, condition) -> tuple[Property, Signal, Score]:
    stmt = (
        select(Property, Signal, Score)
        .join(Signal, Signal.property_id == Property.id)
        .join(Score, Score.property_id == Property.id)
        .where(condition)
    )

    result = await session.execute(stmt)
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    return row


def _build_property_detail_response(row: tuple[Property, Signal, Score]) -> PropertyDetailResponse:
    prop, signal, score = row

    return PropertyDetailResponse(
        property_id=str(prop.id),
        parcel_id=prop.parcel_id,
        address=prop.address,
        raw_address=prop.raw_address,
        city=prop.city,
        state=prop.state,
        zip=prop.zip,
        owner_name=prop.owner_name,
        mailing_address=prop.mailing_address,
        last_sale_date=prop.last_sale_date,
        assessed_value=float(prop.assessed_value) if prop.assessed_value is not None else None,
        signals=SignalDetail(
            absentee_owner=signal.absentee_owner,
            long_term_owner=signal.long_term_owner,
            tax_delinquent=signal.tax_delinquent,
            pre_foreclosure=signal.pre_foreclosure,
            probate=signal.probate,
            eviction=signal.eviction,
            code_violation=signal.code_violation,
        ),
        score=ScoreDetail(
            score=score.score,
            rank=score.rank,
            reason=score.reason,
            scoring_version=score.scoring_version,
            last_updated=score.last_updated,
        ),
        created_at=prop.created_at,
        updated_at=prop.updated_at,
    )
