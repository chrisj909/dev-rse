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
    session: AsyncSession = Depends(get_session),
):
    """Nightly cron endpoint — runs signal detection and scoring on all properties.

    Processes properties in chunks of 250 so each commit is small enough to
    complete reliably on the Supabase pooler without hitting transaction limits.
    """
    if not is_authorized_admin_request(
        settings.cron_secret,
        header_secret=x_cron_secret,
        authorization=authorization,
        query_secret=cron_secret,
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")

    start = time.time()
    total_count_result = await session.execute(select(func.count(Property.id)))
    total = total_count_result.scalar() or 0

    signal_engine = SignalEngine()
    agg_signals: dict[str, int] = {"processed": 0}
    agg_scores: dict[str, int] = {"processed": 0}
    offset = 0

    while offset < total:
        chunk_result = await session.execute(
            select(Property).order_by(Property.id).limit(_CHUNK_SIZE).offset(offset)
        )
        chunk = list(chunk_result.scalars().all())
        if not chunk:
            break

        signal_counts = await signal_engine.process_batch(chunk, session)
        scoring_modes = await ScoringEngine.score_all_modes_batch(chunk, session)
        await session.commit()

        for key, val in signal_counts.items():
            agg_signals[key] = agg_signals.get(key, 0) + val
        broad = scoring_modes.get(DEFAULT_SCORING_MODE, {})
        for key, val in broad.items():
            agg_scores[key] = agg_scores.get(key, 0) + val

        offset += _CHUNK_SIZE

    return {
        "status": "ok",
        "total_properties": total,
        "signals": agg_signals,
        "scores": agg_scores,
        "elapsed_seconds": round(time.time() - start, 2),
    }
