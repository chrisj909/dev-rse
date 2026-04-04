"""
RSE Webhook Runner — Sprint 6, Task 17
scripts/run_webhooks.py

CLI that loads A/B-ranked leads above the score threshold from the database
and fires webhook POSTs via WebhookService.

Usage:
    python scripts/run_webhooks.py [options]

Options:
    --dry-run             Print what would be sent without POSTing anything.
    --threshold INT       Override the score threshold (default: from config).
    --log-level LEVEL     Logging verbosity: DEBUG | INFO | WARNING | ERROR
                          (default: INFO)
    --webhook-url URL     Override the webhook URL (default: from config).
    --rank RANK           Restrict to a single rank band: A | B | C.
                          Defaults to A and B (all leads above threshold that
                          are rank A or B).

Exit codes:
    0 — success (all deliveries succeeded, or dry-run completed)
    1 — one or more webhook deliveries failed
    2 — configuration error (no webhook URL, DB connection failed, etc.)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone

# Ensure backend/ is on the path when run from the repo root or backend/
import os
import pathlib

_BACKEND = pathlib.Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings
from app.models.crm import CRMLeadExport, PropertyExport, ScoreExport, SignalsExport
from app.models.property import Property
from app.models.score import Score
from app.models.signal import Signal
from app.services.webhook import WebhookService

logger = logging.getLogger(__name__)

# Rank bands included by default (A and B — all high-value leads)
_DEFAULT_RANKS = {"A", "B"}


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _load_leads(
    threshold: int,
    ranks: set[str],
) -> list[CRMLeadExport]:
    """
    Query the database for leads at or above `threshold` and in `ranks`.
    Returns a list of CRMLeadExport objects.
    """
    engine = create_async_engine(settings.get_async_database_url(), echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    leads: list[CRMLeadExport] = []
    now = datetime.now(tz=timezone.utc)

    async with session_factory() as session:
        stmt = (
            select(Property, Signal, Score)
            .join(Signal, Signal.property_id == Property.id)
            .join(Score, Score.property_id == Property.id)
            .where(Score.score >= threshold)
            .where(Score.rank.in_(list(ranks)))
            .order_by(Score.score.desc())
        )
        result = await session.execute(stmt)
        rows = result.all()

        for prop, signal, score in rows:
            lead = CRMLeadExport(
                property=PropertyExport(
                    property_id=str(prop.id),
                    parcel_id=prop.parcel_id,
                    address=prop.address,
                    raw_address=prop.raw_address,
                    city=prop.city,
                    state=prop.state,
                    zip=prop.zip,
                    owner_name=prop.owner_name,
                    mailing_address=prop.mailing_address,
                    last_sale_date=prop.last_sale_date,
                    assessed_value=float(prop.assessed_value) if prop.assessed_value is not None else None,
                    created_at=prop.created_at,
                    updated_at=prop.updated_at,
                ),
                signals=SignalsExport(
                    absentee_owner=signal.absentee_owner,
                    long_term_owner=signal.long_term_owner,
                    tax_delinquent=signal.tax_delinquent,
                    pre_foreclosure=signal.pre_foreclosure,
                    probate=signal.probate,
                    eviction=signal.eviction,
                    code_violation=signal.code_violation,
                ),
                score=ScoreExport(
                    value=score.score,
                    rank=score.rank,
                    version=score.scoring_version,
                ),
                tags=list(score.reason) if score.reason else [],
                exported_at=now,
            )
            leads.append(lead)

    await engine.dispose()
    return leads


# ── Main ──────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fire webhook notifications for top-ranked RSE leads.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print leads that would be sent without POSTing to the webhook URL.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=None,
        help=(
            "Minimum score threshold. Leads below this are skipped. "
            f"Defaults to WEBHOOK_SCORE_THRESHOLD from config ({settings.webhook_score_threshold})."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity level.",
    )
    parser.add_argument(
        "--webhook-url",
        default=None,
        help=(
            "Target webhook URL. Overrides WEBHOOK_URL from config. "
            "Required if config WEBHOOK_URL is not set."
        ),
    )
    parser.add_argument(
        "--rank",
        default=None,
        choices=["A", "B", "C"],
        help="Restrict to a single rank band. Defaults to A and B.",
    )
    return parser.parse_args()


async def _main() -> int:
    args = _parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    threshold = args.threshold if args.threshold is not None else settings.webhook_score_threshold
    webhook_url = args.webhook_url or settings.webhook_url
    ranks = {args.rank} if args.rank else _DEFAULT_RANKS

    # Validate configuration
    if not args.dry_run and not webhook_url:
        logger.error(
            "No webhook URL configured. Set WEBHOOK_URL in .env or pass --webhook-url."
        )
        return 2

    logger.info(
        "Loading leads — threshold=%d  ranks=%s  dry_run=%s",
        threshold,
        sorted(ranks),
        args.dry_run,
    )

    try:
        leads = await _load_leads(threshold=threshold, ranks=ranks)
    except Exception as exc:
        logger.error("Failed to load leads from database: %s", exc)
        return 2

    logger.info("Loaded %d lead(s) to process.", len(leads))

    if not leads:
        logger.info("No leads found above threshold — nothing to send.")
        return 0

    if args.dry_run:
        print(f"\n[DRY RUN] Would send {len(leads)} lead(s) to: {webhook_url or '(no URL set)'}\n")
        for lead in leads:
            print(
                f"  {lead.property.parcel_id:20s}  score={lead.score.value:3d}  "
                f"rank={lead.score.rank}  tags={lead.tags}"
            )
        print()
        return 0

    service = WebhookService(
        url=webhook_url,
        threshold=threshold,
        secret=settings.webhook_secret,
    )

    stats = service.send_batch(leads)

    logger.info(
        "Done — sent=%d  failed=%d  skipped=%d",
        stats["sent"],
        stats["failed"],
        stats["skipped"],
    )

    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
