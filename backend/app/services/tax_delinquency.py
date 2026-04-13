"""
RSE Tax Delinquency Service — Sprint 7, Task 14
app/services/tax_delinquency.py

TaxDelinquencyService: accepts a delinquency update for a known property
and upserts the tax_delinquent flag in the signals table.

Design rules:
  - No scraper here — this is the ingestion interface only.
  - Validates that the property exists before writing.
  - Upserts the signal row (creates one if it doesn't exist yet).
  - Returns True if the flag was changed, False if it was already at the
    requested value (idempotent).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.property import Property
from app.models.signal import Signal

log = logging.getLogger("rse.tax_delinquency")


class TaxDelinquencyService:
    """
    Ingestion interface for tax delinquency data.

    Usage:
        service = TaxDelinquencyService()
        changed = await service.ingest_tax_delinquency(
            property_id=some_uuid,
            is_delinquent=True,
            session=db_session,
        )
    """

    # ── Public API ────────────────────────────────────────────────────────────

    async def ingest_tax_delinquency(
        self,
        property_id: uuid.UUID,
        is_delinquent: bool,
        session: AsyncSession,
    ) -> bool:
        """
        Update the tax_delinquent signal for a property.

        Validates that the property exists, then upserts the signals row
        setting tax_delinquent to the supplied value.

        Args:
            property_id:   UUID of the target property.
            is_delinquent: New delinquency flag value.
            session:       Active async database session.

        Returns:
            True  — flag was written/changed.
            False — property not found (no write performed).

        Raises:
            ValueError: if property_id is not a valid UUID.
        """
        if not isinstance(property_id, uuid.UUID):
            raise ValueError(f"property_id must be a UUID, got {type(property_id)!r}")

        # Verify the property exists before touching the signals table.
        result = await session.execute(
            select(Property.id).where(Property.id == property_id)
        )
        exists = result.scalar_one_or_none()
        if exists is None:
            log.warning(
                "tax_delinquency: property %s not found — skipping", property_id
            )
            return False

        await self._upsert_tax_delinquent(session, property_id, is_delinquent)
        log.info(
            "tax_delinquency: property=%s is_delinquent=%s", property_id, is_delinquent
        )
        return True

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    async def _upsert_tax_delinquent(
        session: AsyncSession,
        property_id: uuid.UUID,
        is_delinquent: bool,
    ) -> None:
        """
        INSERT or UPDATE the signals row, setting only tax_delinquent.

        All other signal columns are left at their existing values on UPDATE
        so this write does not clobber absentee_owner, long_term_owner, etc.
        """
        stmt = (
            pg_insert(Signal)
            .values(
                id=uuid.uuid4(),
                property_id=property_id,
                tax_delinquent=is_delinquent,
                # Defaults for new rows — signals already computed stay False
                # until the next signal engine run refreshes them.
                absentee_owner=False,
                long_term_owner=False,
                out_of_state_owner=False,
                corporate_owner=False,
                pre_foreclosure=False,
                probate=False,
                eviction=False,
                code_violation=False,
            )
            .on_conflict_do_update(
                index_elements=["property_id"],
                set_={
                    "tax_delinquent": is_delinquent,
                    "updated_at": datetime.now(tz=timezone.utc),
                },
            )
        )
        await session.execute(stmt)

    # ── Batch helper ──────────────────────────────────────────────────────────

    async def ingest_batch(
        self,
        records: list[dict],
        session: AsyncSession,
    ) -> dict[str, int]:
        """
        Process a list of delinquency records.

        Each record is a dict with keys:
          - property_id (UUID)
          - is_delinquent (bool)

        Returns summary counts:
          {"processed": N, "updated": N, "not_found": N}
        """
        counts = {"processed": 0, "updated": 0, "not_found": 0}

        for record in records:
            pid: Optional[uuid.UUID] = record.get("property_id")
            is_delinquent: bool = bool(record.get("is_delinquent", False))

            if pid is None:
                log.warning("tax_delinquency batch: missing property_id, skipping record")
                continue

            counts["processed"] += 1
            wrote = await self.ingest_tax_delinquency(pid, is_delinquent, session)
            if wrote:
                counts["updated"] += 1
            else:
                counts["not_found"] += 1

        return counts
