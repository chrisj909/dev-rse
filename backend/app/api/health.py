"""
RSE Health Check Endpoints

GET /health    — liveness probe, always 200 when function is running.
GET /health/db — readiness probe, also checks DB connectivity.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_db

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
