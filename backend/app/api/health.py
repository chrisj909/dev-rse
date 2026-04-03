"""
RSE Health Check Endpoint
GET /health — returns 200 with status payload when app + DB are reachable.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Basic liveness + DB connectivity check.
    Returns 200 when the API is running and PostgreSQL is reachable.
    """
    # Verify DB is reachable
    await db.execute(text("SELECT 1"))

    return {
        "status": "ok",
        "service": "Real Estate Signal Engine",
        "database": "connected",
    }
