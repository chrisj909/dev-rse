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

import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
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
from app.scoring.weights import DEFAULT_SCORING_MODE, get_scoring_mode

router = APIRouter(tags=["leads"])
log = logging.getLogger("rse.api.leads")

_SORT_FIELDS = {
    "score": Score.score,
    "assessed_value": Property.assessed_value,
    "last_updated": Score.last_updated,
    "address": Property.address,
    "city": Property.city,
    "county": Property.county,
    "rank": Score.rank,
    "owner_name": Property.owner_name,
}

# Ordered list of all signal column names on the Signal ORM model.
# Order determines the canonical order of active signal names in the response.
_SIGNAL_FIELDS: list[str] = [
    "absentee_owner",
    "long_term_owner",
    "out_of_state_owner",
    "corporate_owner",
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
        property_id=str(getattr(prop, "id", "")),
        county=_coerce_county(getattr(prop, "county", None)),
        parcel_id=str(getattr(prop, "parcel_id", "") or ""),
        address=_coerce_display_address(prop),
        city=_coerce_text(getattr(prop, "city", None)),
        state=_coerce_state(getattr(prop, "state", None)),
        zip=_coerce_text(getattr(prop, "zip", None)),
        owner_name=_coerce_text(getattr(prop, "owner_name", None)),
        mailing_address=_coerce_text(getattr(prop, "mailing_address", None)),
        assessed_value=_coerce_float(getattr(prop, "assessed_value", None)),
        score=_coerce_int(getattr(score, "score", None), default=0),
        rank=_coerce_rank(getattr(score, "rank", None)),
        scoring_mode=_coerce_scoring_mode(getattr(score, "scoring_mode", None)),
        signals=active_signals,
        signal_count=len(active_signals),
        last_updated=_coerce_datetime(getattr(score, "last_updated", None)),
        lat=getattr(prop, "lat", None),
        lng=getattr(prop, "lng", None),
    )


# ââ GET /api/leads/top ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

@router.get("/leads", response_model=LeadsListResponse)
@router.get("/leads/top", response_model=LeadsListResponse)
async def get_top_leads(
    min_score: Optional[int] = Query(default=None, ge=0, description="Minimum score threshold (inclusive)."),
    max_score: Optional[int] = Query(default=None, ge=0, description="Maximum score threshold (inclusive)."),
    absentee_owner: Optional[bool] = Query(default=None, description="Filter to absentee-owned properties only."),
    long_term_owner: Optional[bool] = Query(default=None, description="Filter to long-term owner properties."),
    county: Optional[str] = Query(default=None, description="Filter by county slug: shelby or jefferson."),
    city: Optional[str] = Query(default=None, description="Filter by city name (case-insensitive)."),
    rank: Optional[str] = Query(default=None, description="Filter by rank band: A, B, or C."),
    signals: Optional[str] = Query(default=None, description="Comma-separated active signal filters such as absentee_owner,tax_delinquent."),
    exclude_signals: Optional[str] = Query(default=None, description="Comma-separated signal filters that must be false such as corporate_owner,eviction."),
    signal_match: str = Query(default="all", description="How to apply selected signals: all or any."),
    search: Optional[str] = Query(default=None, description="Search across address, owner name, and parcel ID."),
    owner: Optional[str] = Query(default=None, description="Filter by owner name substring."),
    parcel_id: Optional[str] = Query(default=None, description="Filter by parcel ID substring."),
    min_value: Optional[float] = Query(default=None, ge=0, description="Minimum assessed value (inclusive)."),
    max_value: Optional[float] = Query(default=None, ge=0, description="Maximum assessed value (inclusive)."),
    sort_by: str = Query(default="score", description="Sort field: score, assessed_value, last_updated, address, city, county."),
    sort_dir: str = Query(default="desc", description="Sort direction: asc or desc."),
    scoring_mode: str = Query(default=DEFAULT_SCORING_MODE, description="Scoring lens: broad, owner_occupant, or investor."),
    limit: int = Query(default=50, ge=1, le=250, description="Max results to return (default 50, max 250)."),
    offset: int = Query(default=0, ge=0, description="Result offset for pagination."),
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
    conditions = _build_filter_conditions(
        min_score=min_score,
        max_score=max_score,
        absentee_owner=absentee_owner,
        long_term_owner=long_term_owner,
        county=county,
        city=city,
        rank=rank,
        signals=signals,
        exclude_signals=exclude_signals,
        signal_match=signal_match,
        search=search,
        owner=owner,
        parcel_id=parcel_id,
        min_value=min_value,
        max_value=max_value,
    )
    scoring_mode = _coerce_scoring_mode(scoring_mode)
    order_by = _build_sort_expression(sort_by, sort_dir)

    # Data query â ordered by score DESC
    data_stmt = (
        select(Property, Signal, Score)
        .join(Signal, Signal.property_id == Property.id)
        .join(Score, Score.property_id == Property.id)
        .where(Score.scoring_mode == scoring_mode)
        .order_by(*order_by)
        .limit(limit)
        .offset(offset)
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
        .where(Score.scoring_mode == scoring_mode)
    )
    if conditions:
        count_stmt = count_stmt.where(*conditions)

    count_result = await session.execute(count_stmt)
    total: int = count_result.scalar() or 0

    leads = _build_leads(rows)
    return LeadsListResponse(leads=leads, total=total, limit=limit, offset=offset)


# ââ GET /api/leads/new ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

@router.get("/leads/new", response_model=LeadsListResponse)
async def get_new_leads(
    limit: int = Query(default=50, ge=1, le=1000, description="Max results (default 50, max 1000)."),
    scoring_mode: str = Query(default=DEFAULT_SCORING_MODE, description="Scoring lens: broad, owner_occupant, or investor."),
    session: AsyncSession = Depends(get_db),
) -> LeadsListResponse:
    """
    Return recently updated leads â those scored or re-scored in the last 7 days.

    Ordered by last_updated descending (most recent first).

    Returns:
        LeadsListResponse with matched leads (up to `limit`) and total count.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)
    scoring_mode = _coerce_scoring_mode(scoring_mode)

    data_stmt = (
        select(Property, Signal, Score)
        .join(Signal, Signal.property_id == Property.id)
        .join(Score, Score.property_id == Property.id)
        .where(Score.scoring_mode == scoring_mode)
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
        .where(Score.scoring_mode == scoring_mode)
        .where(Score.last_updated >= cutoff)
    )
    count_result = await session.execute(count_stmt)
    total: int = count_result.scalar() or 0

    leads = _build_leads(rows)
    return LeadsListResponse(leads=leads, total=total)


# ââ GET /api/property/{property_id} ââââââââââââââââââââââââââââââââââââââââââ

@router.get("/property/{property_id}", response_model=PropertyDetailResponse)
async def get_property_detail(
    property_id: str,
    scoring_mode: str = Query(default=DEFAULT_SCORING_MODE, description="Scoring lens: broad, owner_occupant, or investor."),
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

    row = await _fetch_property_detail_row(
        session,
        Property.id == prop_uuid,
        scoring_mode=_coerce_scoring_mode(scoring_mode),
    )
    return _build_property_detail_response(row)


@router.get("/leads/{parcel_id}", response_model=PropertyDetailResponse)
async def get_property_detail_by_parcel_id(
    parcel_id: str,
    county: Optional[str] = Query(default=None, description="Optional county slug to disambiguate duplicate parcel IDs."),
    scoring_mode: str = Query(default=DEFAULT_SCORING_MODE, description="Scoring lens: broad, owner_occupant, or investor."),
    session: AsyncSession = Depends(get_db),
) -> PropertyDetailResponse:
    """Return full property detail using the public parcel_id route key."""
    row = await _fetch_property_detail_row_by_parcel_id(
        session,
        parcel_id=parcel_id,
        county=county,
        scoring_mode=_coerce_scoring_mode(scoring_mode),
    )
    return _build_property_detail_response(row)


# ââ Internal helpers ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def _build_filter_conditions(
    min_score: Optional[int],
    max_score: Optional[int],
    absentee_owner: Optional[bool],
    long_term_owner: Optional[bool],
    county: Optional[str],
    city: Optional[str],
    rank: Optional[str],
    signals: Optional[str],
    exclude_signals: Optional[str],
    signal_match: str,
    search: Optional[str],
    owner: Optional[str],
    parcel_id: Optional[str],
    min_value: Optional[float],
    max_value: Optional[float],
) -> list:
    """
    Build a list of SQLAlchemy WHERE clause conditions from filter params.

    Each condition is appended only when the corresponding param is not None.
    Pass the returned list directly to `.where(*conditions)`.
    """
    conditions = []
    if min_score is not None:
        conditions.append(Score.score >= min_score)
    if max_score is not None:
        conditions.append(Score.score <= max_score)
    if absentee_owner is not None:
        conditions.append(Signal.absentee_owner == absentee_owner)
    if long_term_owner is not None:
        conditions.append(Signal.long_term_owner == long_term_owner)
    if county:
        conditions.append(Property.county == _coerce_county(county))
    if city is not None:
        conditions.append(Property.city.ilike(f"%{city}%"))
    if rank is not None and rank.upper() in {"A", "B", "C"}:
        conditions.append(Score.rank == rank.upper())
    included_signal_names = _coerce_signal_names(signals, parameter_name="signals")
    excluded_signal_names = _coerce_signal_names(exclude_signals, parameter_name="exclude_signals")
    overlapping_signal_names = sorted(set(included_signal_names).intersection(excluded_signal_names))
    if overlapping_signal_names:
        raise HTTPException(
            status_code=422,
            detail=(
                "Conflicting signal filters. The same signal cannot be required and excluded: "
                f"{', '.join(overlapping_signal_names)}."
            ),
        )
    if included_signal_names:
        signal_conditions = [getattr(Signal, signal_name).is_(True) for signal_name in included_signal_names]
        if _coerce_signal_match(signal_match) == "any":
            conditions.append(or_(*signal_conditions))
        else:
            conditions.extend(signal_conditions)
    if excluded_signal_names:
        conditions.extend(getattr(Signal, signal_name).is_(False) for signal_name in excluded_signal_names)
    if search:
        needle = f"%{search}%"
        conditions.append(
            or_(
                Property.address.ilike(needle),
                Property.raw_address.ilike(needle),
                Property.owner_name.ilike(needle),
                Property.parcel_id.ilike(needle),
                Property.county.ilike(needle),
                Property.mailing_address.ilike(needle),
            )
        )
    if owner:
        conditions.append(Property.owner_name.ilike(f"%{owner}%"))
    if parcel_id:
        conditions.append(Property.parcel_id.ilike(f"%{parcel_id}%"))
    if min_value is not None:
        conditions.append(Property.assessed_value >= min_value)
    if max_value is not None:
        conditions.append(Property.assessed_value <= max_value)
    return conditions


def _build_sort_expression(sort_by: str, sort_dir: str) -> tuple:
    sort_field = _SORT_FIELDS.get(sort_by, Score.score)
    direction = sort_dir.lower()
    primary = sort_field.asc() if direction == "asc" else sort_field.desc()
    if sort_by in {"assessed_value", "address", "city", "county", "last_updated", "rank", "owner_name"}:
        primary = primary.nulls_last()
    secondary = Score.score.desc()
    return primary, secondary


async def _fetch_property_detail_row(
    session: AsyncSession,
    condition,
    *,
    scoring_mode: str,
) -> tuple[Property, Signal, Score]:
    stmt = (
        select(Property, Signal, Score)
        .join(Signal, Signal.property_id == Property.id)
        .join(Score, Score.property_id == Property.id)
        .where(Score.scoring_mode == scoring_mode)
        .where(condition)
    )

    result = await session.execute(stmt)
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    return row


async def _fetch_property_detail_row_by_parcel_id(
    session: AsyncSession,
    *,
    parcel_id: str,
    county: Optional[str],
    scoring_mode: str,
) -> tuple[Property, Signal, Score]:
    stmt = (
        select(Property, Signal, Score)
        .join(Signal, Signal.property_id == Property.id)
        .join(Score, Score.property_id == Property.id)
        .where(Score.scoring_mode == scoring_mode)
        .where(Property.parcel_id == parcel_id)
    )
    if county:
        stmt = stmt.where(Property.county == _coerce_county(county))

    result = await session.execute(stmt)
    rows = result.all()
    if not rows:
        raise HTTPException(status_code=404, detail="Property not found.")
    if len(rows) > 1:
        raise HTTPException(status_code=409, detail="Multiple properties matched this parcel ID. Specify county.")
    return rows[0]


def _build_property_detail_response(row: tuple[Property, Signal, Score]) -> PropertyDetailResponse:
    prop, signal, score = row

    return PropertyDetailResponse(
        property_id=str(getattr(prop, "id", "")),
        county=_coerce_county(getattr(prop, "county", None)),
        parcel_id=str(getattr(prop, "parcel_id", "") or ""),
        address=_coerce_display_address(prop),
        raw_address=_coerce_text(getattr(prop, "raw_address", None)),
        city=_coerce_text(getattr(prop, "city", None)),
        state=_coerce_state(getattr(prop, "state", None)),
        zip=_coerce_text(getattr(prop, "zip", None)),
        owner_name=_coerce_text(getattr(prop, "owner_name", None)),
        mailing_address=_coerce_text(getattr(prop, "mailing_address", None)),
        last_sale_date=_coerce_date(getattr(prop, "last_sale_date", None)),
        assessed_value=_coerce_float(getattr(prop, "assessed_value", None)),
        signals=SignalDetail(
            absentee_owner=bool(getattr(signal, "absentee_owner", False)),
            long_term_owner=bool(getattr(signal, "long_term_owner", False)),
            out_of_state_owner=bool(getattr(signal, "out_of_state_owner", False)),
            corporate_owner=bool(getattr(signal, "corporate_owner", False)),
            tax_delinquent=bool(getattr(signal, "tax_delinquent", False)),
            pre_foreclosure=bool(getattr(signal, "pre_foreclosure", False)),
            probate=bool(getattr(signal, "probate", False)),
            eviction=bool(getattr(signal, "eviction", False)),
            code_violation=bool(getattr(signal, "code_violation", False)),
        ),
        score=ScoreDetail(
            score=_coerce_int(getattr(score, "score", None), default=0),
            rank=_coerce_rank(getattr(score, "rank", None)),
            reason=_coerce_reason_list(getattr(score, "reason", None)),
            scoring_mode=_coerce_scoring_mode(getattr(score, "scoring_mode", None)),
            scoring_version=_coerce_text(getattr(score, "scoring_version", None)) or "v3",
            last_updated=_coerce_datetime(getattr(score, "last_updated", None)),
        ),
        created_at=_coerce_datetime(getattr(prop, "created_at", None)),
        updated_at=_coerce_datetime(getattr(prop, "updated_at", None)),
        lat=getattr(prop, "lat", None),
        lng=getattr(prop, "lng", None),
    )


def _build_leads(rows: list[tuple[Property, Signal, Score]]) -> list[LeadResponse]:
    leads: list[LeadResponse] = []
    for prop, signal, score in rows:
        try:
            leads.append(_build_lead(prop, signal, score))
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Skipping malformed lead row for property %s (parcel=%s): %s",
                getattr(prop, "id", "?"),
                getattr(prop, "parcel_id", "?"),
                exc,
            )
    return leads


def _coerce_display_address(prop: Property) -> str | None:
    return (
        _coerce_text(getattr(prop, "address", None))
        or _coerce_text(getattr(prop, "raw_address", None))
        or _coerce_text(getattr(prop, "mailing_address", None))
        or _coerce_text(getattr(prop, "raw_mailing_address", None))
    )


def _coerce_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_state(value: object) -> str:
    state = _coerce_text(value)
    return state.upper() if state else "AL"


def _coerce_county(value: object) -> str:
    county = _coerce_text(value)
    return county.lower() if county else "shelby"


def _coerce_scoring_mode(value: object) -> str:
    try:
        return get_scoring_mode(_coerce_text(value) or DEFAULT_SCORING_MODE).slug
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid scoring_mode. Use broad, owner_occupant, or investor.") from exc


def _coerce_signal_names(value: object, *, parameter_name: str = "signals") -> list[str]:
    raw_value = _coerce_text(value)
    if not raw_value:
        return []

    signal_names = [part.strip().lower() for part in raw_value.split(",") if part.strip()]
    invalid = [signal_name for signal_name in signal_names if signal_name not in _SIGNAL_FIELDS]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {parameter_name} filter. Unsupported values: {', '.join(invalid)}.",
        )
    return list(dict.fromkeys(signal_names))


def _coerce_signal_match(value: object) -> str:
    match_mode = (_coerce_text(value) or "all").lower()
    if match_mode not in {"all", "any"}:
        raise HTTPException(status_code=422, detail="Invalid signal_match. Use all or any.")
    return match_mode


def _coerce_rank(value: object) -> str:
    rank = _coerce_text(value)
    if rank in {"A", "B", "C"}:
        return rank
    return "C"


def _coerce_int(value: object, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _coerce_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    if isinstance(value, str):
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            pass
    return datetime.now(tz=timezone.utc)


def _coerce_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        normalized = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).date()
        except ValueError:
            try:
                return date.fromisoformat(normalized)
            except ValueError:
                return None
    return None


def _coerce_reason_list(value: object) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []
