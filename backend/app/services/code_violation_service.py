"""
RSE Code Violation Service — Sprint 8
app/services/code_violation_service.py

CodeViolationService: matches properties against Birmingham 311 violation
addresses and upserts the code_violation flag in the signals table.

Design rules (mirrors TaxDelinquencyService):
  - No scraping here — accepts a pre-fetched set of violation addresses.
  - Only updates the code_violation column on conflict (other signals untouched).
  - Single bulk upsert for the entire batch.
  - Properties with no address are counted as processed but not flagged.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import Signal
from app.services.address_normalizer import normalize_address

log = logging.getLogger("rse.code_violation")


class CodeViolationService:
    """
    Ingestion interface for Birmingham 311 code violation data.

    Usage:
        from app.scrapers.birmingham_311_scraper import fetch_code_violation_addresses
        violation_addresses = await fetch_code_violation_addresses()
        service = CodeViolationService()
        result = await service.ingest_batch(properties, session, violation_addresses)
    """

    async def ingest_batch(
        self,
        properties: list,
        session: AsyncSession,
        violation_addresses: set[str],
    ) -> dict[str, int]:
        """
        Match properties against 311 violation addresses and upsert code_violation.

        Bulk-upserts all rows in a single SQL statement. Only the code_violation
        column and updated_at are updated on conflict — all other signal columns
        retain their existing values.

        Args:
            properties:          List of Property ORM instances.
            session:             Active async database session.
            violation_addresses: Normalized street addresses with violations (from scraper).

        Returns:
            {"processed": N, "flagged": N}
        """
        counts = {"processed": 0, "flagged": 0}

        if not properties:
            return counts

        now = datetime.now(tz=timezone.utc)
        values: list[dict] = []

        for prop in properties:
            if not prop.address:
                counts["processed"] += 1
                continue

            normalized = normalize_address(prop.address)
            has_violation = bool(normalized and normalized in violation_addresses)

            values.append({
                "id": uuid.uuid4(),
                "property_id": prop.id,
                "code_violation": has_violation,
                # Defaults for rows that don't exist yet
                "absentee_owner": False,
                "long_term_owner": False,
                "out_of_state_owner": False,
                "corporate_owner": False,
                "tax_delinquent": False,
                "pre_foreclosure": False,
                "probate": False,
                "eviction": False,
            })
            counts["processed"] += 1
            if has_violation:
                counts["flagged"] += 1

        if not values:
            return counts

        insert_stmt = pg_insert(Signal)
        await session.execute(
            insert_stmt.values(values).on_conflict_do_update(
                index_elements=["property_id"],
                set_={
                    "code_violation": insert_stmt.excluded.code_violation,
                    "updated_at": now,
                },
            )
        )

        log.info(
            "code_violation: processed=%d flagged=%d",
            counts["processed"],
            counts["flagged"],
        )
        return counts
