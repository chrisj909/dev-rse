"""
POST /api/ingest/run â pull data from all scrapers, upsert into properties table,
run signal + scoring engines on new/updated records.
Secured with CRON_SECRET via bearer auth, X-Cron-Secret, or query param.
"""
import logging
import time
from datetime import datetime, timedelta, timezone

log = logging.getLogger("rse.ingest")

from fastapi import APIRouter, Header, HTTPException, Depends, Query
from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin_auth import is_authorized_admin_request
from app.core.config import settings
from app.db.session import get_session
from app.models.property import Property
from app.scoring.engine import ScoringEngine
from app.scoring.weights import DEFAULT_SCORING_MODE
from app.scrapers import run_all_scrapers_with_metadata, run_delinquent_only
from app.scrapers.birmingham_311_scraper import fetch_code_violation_addresses
from app.services.code_violation_service import CodeViolationService
from app.services.tax_delinquency import TaxDelinquencyService
from app.signals.engine import SignalEngine

router = APIRouter()


def _normalize_updated_since(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _resolve_updated_since(
    updated_since: datetime | None,
    delta_days: int | None,
) -> datetime | None:
    if updated_since is not None and delta_days is not None:
        raise HTTPException(
            status_code=400,
            detail="Pass either updated_since or delta_days, not both.",
        )
    if updated_since is not None:
        return _normalize_updated_since(updated_since)
    if delta_days is not None:
        return datetime.now(tz=timezone.utc) - timedelta(days=delta_days)
    return None


@router.post("/ingest/run")
async def run_ingest(
    x_cron_secret: str = Header(None),
    authorization: str = Header(None),
    cron_secret: str = Query(None),
    county: str = Query("all"),
    delinquent_only: bool = Query(False),
    dry_run: bool = Query(False),
    limit: int = Query(None),
    start_offset: int = Query(
        default=0,
        ge=0,
        description="Result offset for chunked single-county ingest runs.",
    ),
    updated_since: datetime | None = Query(
        default=None,
        description="UTC timestamp cutoff for changed-since retrieval, e.g. 2026-04-13T00:00:00Z.",
    ),
    delta_days: int | None = Query(
        default=None,
        ge=1,
        le=30,
        description="Shortcut for incremental retrieval over the last N days.",
    ),
    session: AsyncSession = Depends(get_session),
):
    """Run scrapers and ingest data. Secured with CRON_SECRET."""
    if settings.cron_secret and not is_authorized_admin_request(
        settings.cron_secret,
        header_secret=x_cron_secret,
        authorization=authorization,
        query_secret=cron_secret,
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")

    start = time.time()
    resolved_updated_since = _resolve_updated_since(updated_since, delta_days)
    normalized_county = county.lower()

    if delinquent_only and resolved_updated_since is not None:
        raise HTTPException(
            status_code=400,
            detail="Incremental retrieval is not supported for delinquent_only runs.",
        )

    if start_offset and normalized_county == "all":
        raise HTTPException(
            status_code=400,
            detail="start_offset is only supported for single-county ingest runs.",
        )

    try:
        if delinquent_only:
            records = await run_delinquent_only(county=county)
            primary_fetched = len(records)
        else:
            scrape_result = await run_all_scrapers_with_metadata(
                limit=limit,
                county=county,
                updated_since=resolved_updated_since,
                start_offset=start_offset,
            )
            records = scrape_result["records"]
            primary_fetched = scrape_result["primary_fetched"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scraper error: {str(e)}")

    fetched = len(records)
    next_offset = start_offset + primary_fetched if primary_fetched else None
    has_more = bool(limit and primary_fetched == limit and not delinquent_only and normalized_county != "all")

    if dry_run:
        return {
            "status": "dry_run",
            "retrieval": {
                "mode": "incremental" if resolved_updated_since else "full",
                "updated_since": resolved_updated_since.isoformat() if resolved_updated_since else None,
                "delta_days": delta_days,
                "start_offset": start_offset,
                "next_offset": next_offset,
                "has_more": has_more,
            },
            "fetched": fetched,
            "sample": records[:5],
            "elapsed_seconds": round(time.time() - start, 2),
        }

    upserted = 0
    property_keys: list[tuple[str, str]] = []
    for rec in records:
        parcel_id = rec.get("parcel_id")
        property_county = str(rec.get("county") or "shelby").lower()
        if not parcel_id:
            continue

        mailing_address = rec.get("mailing_address") or rec.get("owner_mailing_address")
        stmt = pg_insert(Property).values(
            county=property_county,
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
            lat=rec.get("lat"),
            lng=rec.get("lng"),
        ).on_conflict_do_update(
            index_elements=["county", "parcel_id"],
            set_={
                "county": property_county,
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
                "lat": rec.get("lat"),
                "lng": rec.get("lng"),
            },
        )
        await session.execute(stmt)
        property_keys.append((property_county, parcel_id))
        upserted += 1

    # Flush so property rows are visible within this transaction for the
    # signal/scoring reload below, but hold the commit until all three
    # layers (properties + signals + scores) are ready to land together.
    await session.flush()

    signal_engine = SignalEngine()
    tax_service = TaxDelinquencyService()
    code_violation_svc = CodeViolationService()
    tax_delinquency_by_parcel = {
        rec.get("parcel_id"): bool(rec.get("is_tax_delinquent", False))
        for rec in records
        if rec.get("parcel_id")
    }
    signal_result = {"processed": upserted}
    score_result: dict[str, object] = {"processed": 0}
    tax_result = {"processed": 0, "updated": 0, "not_found": 0}
    code_violation_result: dict[str, int] = {"processed": 0, "flagged": 0}

    # Fetch 311 violation addresses once per ingest run (Jefferson county only).
    violation_addresses: set[str] = set()
    if normalized_county in ("jefferson", "all"):
        try:
            violation_addresses = await fetch_code_violation_addresses()
        except Exception as exc:
            log.warning("Birmingham 311 fetch failed, skipping code_violation: %s", exc)

    try:
        unique_keys = list(dict.fromkeys(property_keys))
        result = await session.execute(
            select(Property).where(
                tuple_(Property.county, Property.parcel_id).in_(unique_keys)
            )
        )
        properties = list(result.scalars().all())
        signal_result = await signal_engine.process_batch(properties, session)
        tax_records = [
            {
                "property_id": prop.id,
                "is_delinquent": tax_delinquency_by_parcel.get(prop.parcel_id, False),
            }
            for prop in properties
        ]
        tax_result = await tax_service.ingest_batch(tax_records, session)
        code_violation_result = await code_violation_svc.ingest_batch(
            properties, session, violation_addresses
        )
        scoring_modes = await ScoringEngine.score_all_modes_batch(properties, session)
        score_result = dict(scoring_modes.get(DEFAULT_SCORING_MODE, {}))
        score_result["modes"] = scoring_modes
        await session.commit()
    except Exception as e:
        await session.rollback()
        signal_result = {"error": str(e)}
        score_result = {"error": str(e)}

    return {
        "status": "ok",
        "county": county.lower(),
        "retrieval": {
            "mode": "incremental" if resolved_updated_since else "full",
            "updated_since": resolved_updated_since.isoformat() if resolved_updated_since else None,
            "delta_days": delta_days,
            "start_offset": start_offset,
            "next_offset": next_offset,
            "has_more": has_more,
        },
        "fetched": fetched,
        "upserted": upserted,
        "signals": signal_result,
        "tax_delinquency": tax_result,
        "code_violation": code_violation_result,
        "scoring": score_result,
        "elapsed_seconds": round(time.time() - start, 2),
    }
