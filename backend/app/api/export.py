"""
RSE CRM Export Endpoints — Sprint 6, Task 16
app/api/export.py

Routes:
  GET /api/leads/export          — paginated CRM export of top leads
  GET /api/leads/export/{id}     — single-property CRM export

Query params (collection endpoint):
  min_score  int    — minimum score threshold (inclusive, default: none)
  rank       str    — filter by rank letter: "A" | "B" | "C"
  limit      int    — result cap (default 100, max 500)
  format     str    — response format; "json" only for now (reserved for csv/xml later)

Both endpoints return data in the CRMLeadExport / CRMExportResponse format
defined in app/models/crm.py — a stable contract for downstream CRM tools
and the WebhookService.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.crm import (
    CRMExportResponse,
    CRMLeadExport,
    PropertyExport,
    ScoreExport,
    SignalsExport,
)
from app.models.property import Property
from app.models.score import Score
from app.models.signal import Signal

router = APIRouter(prefix="/api", tags=["export"])

# Rank values the API accepts — validated explicitly to give a clean 422.
_VALID_RANKS = {"A", "B", "C"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_crm_lead(
    prop: Property,
    signal: Signal,
    score: Score,
    now: datetime,
) -> CRMLeadExport:
    """Assemble a CRMLeadExport from ORM rows."""
    return CRMLeadExport(
        property=PropertyExport(
            property_id=str(prop.id),
            parcel_id=prop.parcel_id,
            address=prop.address,
            raw_address=prop.raw_address,
            city=prop.city,
            state=prop.state,
            zip=prop.zip,
            owner_name=prop.owner_name,
            mailing_address=prop.mailing_address,
            last_sale_date=prop.last_sale_date if isinstance(prop.last_sale_date, date) else None,
            assessed_value=float(prop.assessed_value) if prop.assessed_value is not None else None,
            created_at=prop.created_at,
            updated_at=prop.updated_at,
        ),
        signals=SignalsExport(
            absentee_owner=signal.absentee_owner,
            long_term_owner=signal.long_term_owner,
            tax_delinquent=signal.tax_delinquent,
            pre_foreclosure=signal.pre_foreclosure,
            probate=signal.probate,
            eviction=signal.eviction,
            code_violation=signal.code_violation,
        ),
        score=ScoreExport(
            value=score.score,
            rank=score.rank,
            version=score.scoring_version,
        ),
        tags=list(score.reason) if score.reason else [],
        exported_at=now,
    )


def _build_export_conditions(
    min_score: Optional[int],
    rank: Optional[str],
) -> list:
    """Build SQLAlchemy WHERE conditions from export filter params."""
    conditions = []
    if min_score is not None:
        conditions.append(Score.score >= min_score)
    if rank is not None:
        conditions.append(Score.rank == rank.upper())
    return conditions


# ── GET /api/leads/export ─────────────────────────────────────────────────────

@router.get("/leads/export", response_model=CRMExportResponse)
async def export_leads(
    min_score: Optional[int] = Query(
        default=None,
        ge=0,
        description="Minimum score threshold (inclusive).",
    ),
    rank: Optional[str] = Query(
        default=None,
        description="Filter by rank letter: A, B, or C.",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Max results to return (default 100, max 500).",
    ),
    format: str = Query(
        default="json",
        description="Response format — 'json' only for now.",
    ),
    session: AsyncSession = Depends(get_db),
) -> CRMExportResponse:
    """
    Export leads in CRM-ready format.

    Returns properties joined with their signals and scores, shaped as
    CRMLeadExport records — a stable, versioned contract for external CRM
    tools and the webhook pipeline.

    Filtering:
      - `min_score`: exclude properties below this score
      - `rank`: restrict to a single rank band (A, B, or C)
      - `limit`: cap the result set (max 500)
      - `format`: reserved — only "json" is supported

    `total` in the response reflects the count of matching records before
    the limit is applied.
    """
    if format.lower() != "json":
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{format}'. Only 'json' is supported.",
        )

    if rank is not None and rank.upper() not in _VALID_RANKS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid rank '{rank}'. Must be one of: A, B, C.",
        )

    conditions = _build_export_conditions(min_score, rank)

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

    count_stmt = (
        select(func.count(Property.id))
        .join(Signal, Signal.property_id == Property.id)
        .join(Score, Score.property_id == Property.id)
    )
    if conditions:
        count_stmt = count_stmt.where(*conditions)

    count_result = await session.execute(count_stmt)
    total: int = count_result.scalar() or 0

    now = datetime.now(tz=timezone.utc)
    leads = [_build_crm_lead(prop, signal, score, now) for prop, signal, score in rows]

    return CRMExportResponse(leads=leads, total=total, exported_at=now)


# ── GET /api/leads/export/{property_id} ──────────────────────────────────────

@router.get("/leads/export/{property_id}", response_model=CRMLeadExport)
async def export_lead_by_id(
    property_id: str,
    session: AsyncSession = Depends(get_db),
) -> CRMLeadExport:
    """
    Export a single property in CRM-ready format.

    Raises:
        400 Bad Request — if `property_id` is not a valid UUID.
        404 Not Found   — if the property doesn't exist, or lacks signal/score data.
    """
    try:
        prop_uuid = uuid.UUID(property_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid property ID — must be a valid UUID.",
        )

    stmt = (
        select(Property, Signal, Score)
        .join(Signal, Signal.property_id == Property.id)
        .join(Score, Score.property_id == Property.id)
        .where(Property.id == prop_uuid)
    )

    result = await session.execute(stmt)
    row = result.one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail="Property not found.")

    prop, signal, score = row
    now = datetime.now(tz=timezone.utc)
    return _build_crm_lead(prop, signal, score, now)
