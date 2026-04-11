"""
POST /api/ingest/run â pull data from all scrapers, upsert into properties table,
run signal + scoring engines on new/updated records.
Secured with X-Cron-Secret header (reuses CRON_SECRET env var).
"""
import time
from fastapi import APIRouter, Header, HTTPException, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.db.session import get_session
from app.models.property import Property
from app.scoring.engine import ScoringEngine
from app.scrapers import run_all_scrapers, run_delinquent_only
from app.services.tax_delinquency import TaxDelinquencyService
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
    parcel_ids: list[str] = []
    for rec in records:
        parcel_id = rec.get("parcel_id")
        if not parcel_id:
            continue

        mailing_address = rec.get("mailing_address") or rec.get("owner_mailing_address")
        stmt = pg_insert(Property).values(
            parcel_id=parcel_id,
            address=rec.get("address"),
            raw_address=rec.get("raw_address") or rec.get("address"),
            city=rec.get("city"),
            state=rec.get("state") or "AL",
            zip=rec.get("zip"),
            owner_name=rec.get("owner_name"),
            mailing_address=mailing_address,
            raw_mailing_address=rec.get("raw_mailing_address") or mailing_address,
            last_sale_date=rec.get("last_sale_date"),
            assessed_value=rec.get("assessed_value"),
        ).on_conflict_do_update(
            index_elements=["parcel_id"],
            set_={
                "address": rec.get("address"),
                "raw_address": rec.get("raw_address") or rec.get("address"),
                "city": rec.get("city"),
                "state": rec.get("state") or "AL",
                "zip": rec.get("zip"),
                "owner_name": rec.get("owner_name"),
                "mailing_address": mailing_address,
                "raw_mailing_address": rec.get("raw_mailing_address") or mailing_address,
                "last_sale_date": rec.get("last_sale_date"),
                "assessed_value": rec.get("assessed_value"),
            },
        )
        await session.execute(stmt)
        parcel_ids.append(parcel_id)
        upserted += 1

    await session.commit()

    signal_engine = SignalEngine()
    scoring_engine = ScoringEngine()
    tax_service = TaxDelinquencyService()
    tax_delinquency_by_parcel = {
        rec.get("parcel_id"): bool(rec.get("is_tax_delinquent", False))
        for rec in records
        if rec.get("parcel_id")
    }
    signal_result = {"processed": upserted}
    score_result = {"processed": 0}
    tax_result = {"processed": 0, "updated": 0, "not_found": 0}
    try:
        result = await session.execute(
            select(Property).where(
                Property.parcel_id.in_(list(dict.fromkeys(parcel_ids)))
            )
        )
        properties = result.scalars().all()
        signal_result = await signal_engine.process_batch(properties, session)
        tax_records = [
            {
                "property_id": prop.id,
                "is_delinquent": tax_delinquency_by_parcel.get(prop.parcel_id, False),
            }
            for prop in properties
        ]
        tax_result = await tax_service.ingest_batch(tax_records, session)
        score_result = await scoring_engine.score_batch(properties, session)
        await session.commit()
    except Exception as e:
        await session.rollback()
        signal_result = {"error": str(e)}

    return {
        "status": "ok",
        "fetched": fetched,
        "upserted": upserted,
        "signals": signal_result,
        "tax_delinquency": tax_result,
        "scoring": score_result,
        "elapsed_seconds": round(time.time() - start, 2),
    }
