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
from app.scoring.weights import SCORING_MODES

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
    scores_by_mode = {mode: 0 for mode in SCORING_MODES}
    scores_by_mode.update({row[0]: row[1] for row in score_rows})

    score_mode_constraint_result = await db.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_constraint constraint_row
                JOIN pg_class table_row ON table_row.oid = constraint_row.conrelid
                WHERE table_row.relname = 'scores'
                  AND constraint_row.conname = 'uq_scores_property_mode'
            )
            """
        )
    )
    has_property_mode_constraint = bool(score_mode_constraint_result.scalar())

    return {
        "properties": total_properties,
        "signals": total_signals,
        "scores": scores_by_mode,
        "score_schema": {
            "property_mode_unique_constraint": has_property_mode_constraint,
        },
    }
