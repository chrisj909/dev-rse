import time

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin_auth import is_authorized_admin_request
from app.db.session import get_session
from app.core.config import settings
from app.models.property import Property
from app.scoring.engine import ScoringEngine
from app.scoring.weights import DEFAULT_SCORING_MODE
from app.signals.engine import SignalEngine

router = APIRouter()

_CHUNK_SIZE = 250


@router.get("/run-signals")
async def run_signals_cron(
    x_cron_secret: str = Header(None),
    authorization: str = Header(None),
    cron_secret: str = Query(None),
    offset: int = Query(default=0, ge=0, description="Row offset for paginated rescore runs."),
    limit: int = Query(default=_CHUNK_SIZE, ge=1, le=500, description="Properties to process per call."),
    session: AsyncSession = Depends(get_session),
):
    """Signal detection and scoring endpoint.

    Processes one chunk of properties per call so it fits within Vercel's
    60-second serverless limit.  Returns has_more + next_offset so callers
    can page through the full table by looping.

    The Vercel daily cron fires this once (offset=0) to refresh the most
    recently updated records.  The ingest UI rescore flow calls it in a loop
    until has_more is false.
    """
    if not is_authorized_admin_request(
        settings.cron_secret,
        header_secret=x_cron_secret,
        authorization=authorization,
        query_secret=cron_secret,
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")

    start = time.time()

    total_result = await session.execute(select(func.count(Property.id)))
    total = total_result.scalar() or 0

    chunk_result = await session.execute(
        select(Property).order_by(Property.id).limit(limit).offset(offset)
    )
    chunk = list(chunk_result.scalars().all())

    signal_engine = SignalEngine()
    signal_counts: dict = {"processed": 0}
    scoring_counts: dict = {"processed": 0}

    try:
        if chunk:
            signal_counts = await signal_engine.process_batch(chunk, session)
            scoring_modes = await ScoringEngine.score_all_modes_batch(chunk, session)
            scoring_counts = dict(scoring_modes.get(DEFAULT_SCORING_MODE, {}))
            await session.commit()
    except Exception as e:
        await session.rollback()
        return {
            "status": "error",
            "error": str(e),
            "total_properties": total,
            "offset": offset,
            "processed": 0,
            "elapsed_seconds": round(time.time() - start, 2),
        }

    next_offset = offset + len(chunk)
    has_more = next_offset < total

    return {
        "status": "ok",
        "total_properties": total,
        "offset": offset,
        "next_offset": next_offset,
        "has_more": has_more,
        "processed": len(chunk),
        "signals": signal_counts,
        "scores": scoring_counts,
        "elapsed_seconds": round(time.time() - start, 2),
    }
