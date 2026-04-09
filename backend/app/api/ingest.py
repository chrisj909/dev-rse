"""
POST /api/ingest/run — pull data from all scrapers, upsert into properties table,
run signal engine on new/updated records.
Secured with X-Cron-Secret header (reuses CRON_SECRET env var).
"""
import time
from fastapi import APIRouter, Header, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.db.session import get_session
from app.models.property import Property
from app.scrapers import run_all_scrapers, run_delinquent_only
from app.signals.engine import SignalEngine
from app.core.config import settings

router = APIRouter()


@router.post("/ingest/run")
async def run_ingest(
    x_cron_secret: str = Header(None),
    delinquent_only: bool = Query(False),
    dry_run: bool = Query(False),
    limit: int = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Run scrapers and ingest data. Secured with CRON_SECRET."""
    if settings.cron_secret and x_cron_secret != settings.cron_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")

    start = time.time()

    try:
        if delinquent_only:
            records = await run_delinquent_only()
        else:
            records = await run_all_scrapers(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scraper error: {str(e)}")

    fetched = len(records)

    if dry_run:
        return {
            "status": "dry_run",
            "fetched": fetched,
            "sample": records[:5],
            "elapsed_seconds": round(time.time() - start, 2),
        }

    upserted = 0
    for rec in records:
        if not rec.get("parcel_id"):
            continue
        stmt = pg_insert(Property).values(
            parcel_id=rec["parcel_id"],
            address=rec.get("address"),
            city=rec.get("city"),
            owner_name=rec.get("owner_name"),
            owner_mailing_address=rec.get("owner_mailing_address"),
            assessed_value=rec.get("assessed_value"),
            is_tax_delinquent=rec.get("is_tax_delinquent", False),
            is_absentee_owner=rec.get("is_absentee_owner", False),
            is_probate=rec.get("is_probate", False),
            is_pre_foreclosure=rec.get("is_pre_foreclosure", False),
            long_term_owner_years=rec.get("long_term_owner_years"),
            raw_data=rec.get("raw_data", {}),
        ).on_conflict_do_update(
            index_elements=["parcel_id"],
            set_={
                "address": rec.get("address"),
                "city": rec.get("city"),
                "owner_name": rec.get("owner_name"),
                "is_tax_delinquent": rec.get("is_tax_delinquent", False),
                "is_absentee_owner": rec.get("is_absentee_owner", False),
                "raw_data": rec.get("raw_data", {}),
            },
        )
        await session.execute(stmt)
        upserted += 1

    await session.commit()

    engine = SignalEngine()
    signal_result = {"processed": upserted}
    try:
        from sqlalchemy import select
        result = await session.execute(
            select(Property).where(
                Property.parcel_id.in_([r["parcel_id"] for r in records[:500]])
            )
        )
        properties = result.scalars().all()
        signal_result = engine.process_batch(properties, session)
        await session.commit()
    except Exception as e:
        signal_result = {"error": str(e)}

    return {
        "status": "ok",
        "fetched": fetched,
        "upserted": upserted,
        "signals": signal_result,
        "elapsed_seconds": round(time.time() - start, 2),
    }
