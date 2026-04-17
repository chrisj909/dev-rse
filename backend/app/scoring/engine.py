"""
RSE Scoring Engine — Sprint 3, Task 10
app/scoring/engine.py

ScoringEngine: reads signal flags for each property from the DB,
applies versioned weights via calculate_score(), and upserts the
result (score + rank + reason tags + scoring_version) to the scores table.

Design rules (from BUILD_PLAN):
  - Reads Signal rows from DB; calculates score using pure calculate_score().
  - Upserts Score rows (one per property — unique on property_id).
  - Supports single-property mode (score) and batch mode (score_batch).
  - scoring_version is stored on every score row.
  - Missing signal row → score = 0, rank = "C", reasons = [].
  - Batch mode returns rank distribution counts + error count.
  - Errors on one property do not abort the batch.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.property import Property
from app.models.score import Score
from app.models.signal import Signal
from app.scoring.weights import (
    DEFAULT_SCORING_MODE,
    SCORING_MODES,
    SCORING_VERSION,
    calculate_score_for_mode,
    get_scoring_mode,
)

log = logging.getLogger("rse.scoring_engine")

# All signal columns read from the Signal model (must match column names exactly)
_SIGNAL_COLUMNS = [
    "absentee_owner",
    "long_term_owner",
    "out_of_state_owner",
    "corporate_owner",
    "tax_delinquent",
    "pre_foreclosure",
    "probate",
    "code_violation",
]


class ScoringEngine:
    """
    Batch-capable scoring engine.

    Usage (single property):
        engine = ScoringEngine()
        result = await engine.score(prop, session)
        # {"score": 25, "rank": "A", "reasons": ["absentee_owner", "long_term_owner"]}

    Usage (batch):
        summary = await engine.score_batch(properties, session)
        # {"processed": 50, "rank_a": 10, "rank_b": 20, "rank_c": 20, "errors": 0}
    """

    def __init__(
        self,
        scoring_version: str = SCORING_VERSION,
        scoring_mode: str = DEFAULT_SCORING_MODE,
    ) -> None:
        """
        Args:
            scoring_version: Weight version string stored on every score row.
                             Defaults to the current module-level SCORING_VERSION.
        """
        self._scoring_version = scoring_version
        self._scoring_mode = get_scoring_mode(scoring_mode).slug

    # ── Single-property scoring ───────────────────────────────────────────────

    async def score(
        self,
        prop: Property,
        session: AsyncSession,
        *,
        signal_row: Optional[Signal] = None,
    ) -> dict:
        """
        Score a single property: read its signals, calculate score/rank/reasons,
        and upsert the result to the scores table.

        Args:
            prop:       SQLAlchemy Property ORM instance.
            session:    Active async database session.
            signal_row: Pre-loaded Signal row (avoids a DB round-trip when
                        score_batch has already bulk-fetched signals).

        Returns:
            Dict with keys:
              score   (int)       — total weighted score
              rank    (str)       — "A", "B", or "C"
              reasons (list[str]) — active signal tags (+ "distress_combo" if triggered)

        Note:
            If no signal row exists for this property, score is 0 / rank "C".
            The caller is responsible for committing the session after a batch.
        """
        if signal_row is None:
            result = await session.execute(
                select(Signal).where(Signal.property_id == prop.id)
            )
            signal_row = result.scalar_one_or_none()

        if signal_row is None:
            flags: dict[str, bool] = {}
            log.warning(
                "No signal row found for property %s (parcel=%s) — scoring as 0",
                prop.id,
                getattr(prop, "parcel_id", "?"),
            )
        else:
            flags = {col: getattr(signal_row, col, False) for col in _SIGNAL_COLUMNS}

        score_val, rank, reasons = calculate_score_for_mode(flags, mode=self._scoring_mode)

        await self._upsert_score(session, prop.id, score_val, rank, reasons)

        log.debug(
            "property=%s parcel=%s mode=%s score=%d rank=%s reasons=%s version=%s",
            prop.id,
            getattr(prop, "parcel_id", "?"),
            self._scoring_mode,
            score_val,
            rank,
            reasons,
            self._scoring_version,
        )

        return {
            "score": score_val,
            "rank": rank,
            "reasons": reasons,
            "scoring_mode": self._scoring_mode,
        }

    # ── Batch scoring ─────────────────────────────────────────────────────────

    async def score_batch(
        self,
        properties: Sequence[Property],
        session: AsyncSession,
    ) -> dict[str, int]:
        """
        Score a list of properties through the scoring engine.

        Bulk-loads all signal rows for the batch in one query so the per-property
        score() call never issues an individual SELECT.  The session is NOT
        committed here — the caller should commit after each batch.

        Args:
            properties: Sequence of SQLAlchemy Property ORM instances.
            session:    Active async database session.

        Returns:
            Summary dict:
              {
                "processed": int,  — total properties successfully scored
                "rank_a":    int,  — count of rank A results
                "rank_b":    int,  — count of rank B results
                "rank_c":    int,  — count of rank C results
                "errors":    int,  — properties that raised an exception
              }
        """
        counts: dict[str, int] = {
            "processed": 0,
            "rank_a": 0,
            "rank_b": 0,
            "rank_c": 0,
            "errors": 0,
        }

        # Bulk-load all signal rows for this batch — one query instead of N.
        property_ids = [prop.id for prop in properties]
        signal_map: dict = {}
        if property_ids:
            signal_rows = (
                await session.execute(
                    select(Signal).where(Signal.property_id.in_(property_ids))
                )
            ).scalars().all()
            signal_map = {row.property_id: row for row in signal_rows}

        for prop in properties:
            try:
                async with session.begin_nested():
                    result = await self.score(prop, session, signal_row=signal_map.get(prop.id))
                counts["processed"] += 1
                rank_key = f"rank_{result['rank'].lower()}"
                counts[rank_key] = counts.get(rank_key, 0) + 1
            except Exception as exc:  # noqa: BLE001
                log.error(
                    "Failed to score property %s (parcel=%s): %s",
                    getattr(prop, "id", "?"),
                    getattr(prop, "parcel_id", "?"),
                    exc,
                )
                counts["errors"] += 1

        return counts

    @classmethod
    async def score_all_modes_batch(
        cls,
        properties: Sequence[Property],
        session: AsyncSession,
        scoring_version: str = SCORING_VERSION,
    ) -> dict[str, dict[str, int]]:
        """Score a property set for every configured scoring mode."""
        results: dict[str, dict[str, int]] = {}
        for mode in SCORING_MODES:
            engine = cls(scoring_version=scoring_version, scoring_mode=mode)
            results[mode] = await engine.score_batch(properties, session)
        return results

    # ── DB helpers ────────────────────────────────────────────────────────────

    async def _upsert_score(
        self,
        session: AsyncSession,
        property_id: uuid.UUID,
        score: int,
        rank: str,
        reasons: list[str],
    ) -> None:
        """
        INSERT or UPDATE a score row for the given property_id.

        Uses PostgreSQL's ON CONFLICT DO UPDATE so repeated scoring runs
        are idempotent — the latest score always wins.

        The scoring_version and last_updated timestamp are always refreshed.
        """
        new_id = uuid.uuid4()
        now = datetime.now(tz=timezone.utc)

        stmt = (
            pg_insert(Score)
            .values(
                id=new_id,
                property_id=property_id,
                scoring_mode=self._scoring_mode,
                score=score,
                rank=rank,
                reason=reasons,
                scoring_version=self._scoring_version,
                last_updated=now,
            )
            .on_conflict_do_update(
                index_elements=["property_id", "scoring_mode"],
                set_={
                    "score": score,
                    "rank": rank,
                    "reason": reasons,
                    "scoring_version": self._scoring_version,
                    "last_updated": now,
                },
            )
        )
        await session.execute(stmt)
