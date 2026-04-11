import time
from fastapi import APIRouter, Header, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_session
from app.signals.engine import SignalEngine
from app.models.property import Property
from app.scoring.engine import ScoringEngine
from app.core.config import settings

router = APIRouter()


@router.get("/run-signals")
async def run_signals_cron(
    x_cron_secret: str = Header(None),
    session: AsyncSession = Depends(get_session),
):
    """Nightly cron endpoint — runs signal detection and scoring on all properties."""
    if not settings.cron_secret or x_cron_secret != settings.cron_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")

    start = time.time()
    result = await session.execute(select(Property))
    properties = result.scalars().all()

    signal_engine = SignalEngine()
    scoring_engine = ScoringEngine()

    signal_counts = await signal_engine.process_batch(properties, session)
    scoring_counts = await scoring_engine.score_batch(properties, session)
    await session.commit()
    elapsed = round(time.time() - start, 2)

    return {
        "status": "ok",
        "processed": signal_counts.get("processed", len(properties)),
        "signals": signal_counts,
        "scores": scoring_counts,
        "elapsed_seconds": elapsed,
    }
