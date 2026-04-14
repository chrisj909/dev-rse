import time

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin_auth import is_authorized_admin_request
from app.db.session import get_session
from app.core.config import settings
from app.models.property import Property
from app.scoring.engine import ScoringEngine
from app.scoring.weights import DEFAULT_SCORING_MODE
from app.signals.engine import SignalEngine

router = APIRouter()


@router.get("/run-signals")
async def run_signals_cron(
    x_cron_secret: str = Header(None),
    authorization: str = Header(None),
    cron_secret: str = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Nightly cron endpoint — runs signal detection and scoring on all properties."""
    if not is_authorized_admin_request(
        settings.cron_secret,
        header_secret=x_cron_secret,
        authorization=authorization,
        query_secret=cron_secret,
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")

    start = time.time()
    result = await session.execute(select(Property))
    properties = list(result.scalars().all())

    signal_engine = SignalEngine()
    signal_counts = await signal_engine.process_batch(properties, session)
    scoring_modes = await ScoringEngine.score_all_modes_batch(properties, session)
    scoring_counts: dict[str, object] = dict(scoring_modes.get(DEFAULT_SCORING_MODE, {}))
    scoring_counts["modes"] = scoring_modes
    await session.commit()
    elapsed = round(time.time() - start, 2)

    return {
        "status": "ok",
        "processed": signal_counts.get("processed", len(properties)),
        "signals": signal_counts,
        "scores": scoring_counts,
        "elapsed_seconds": elapsed,
    }
