"""
RSE Health Check Endpoints

GET /health       — liveness probe, always 200 when function is running.
GET /health/db    — readiness probe, also checks DB connectivity.
GET /health/stats — row counts for properties, signals, and scores per mode.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, text

from app.db.session import get_db
from app.models.property import Property
from app.models.score import Score
from app.models.signal import Signal

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """
    Liveness probe — returns 200 whenever the serverless function is running.
    No DB dependency so it never blocks on an unconfigured database.
    """
    return {
        "status": "ok",
        "service": "Real Estate Signal Engine",
    }


@router.get("/health/db")
async def health_check_db(db: AsyncSession = Depends(get_db)):
    """
    Readiness probe — returns 200 only when both the API and PostgreSQL are up.
    """
    await db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "service": "Real Estate Signal Engine",
        "database": "connected",
    }


@router.get("/health/stats")
async def health_stats(db: AsyncSession = Depends(get_db)):
    """
    Row counts for properties, signals, and scores per scoring mode.
    Useful for verifying that an ingest actually persisted data.
    """
    total_properties = (await db.execute(select(func.count(Property.id)))).scalar() or 0
    total_signals = (await db.execute(select(func.count(Signal.id)))).scalar() or 0

    score_rows = (
        await db.execute(
            select(Score.scoring_mode, func.count(Score.id))
            .group_by(Score.scoring_mode)
        )
    ).all()
    scores_by_mode = {row[0]: row[1] for row in score_rows}

    return {
        "properties": total_properties,
        "signals": total_signals,
        "scores": scores_by_mode,
    }
