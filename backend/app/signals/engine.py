"""
RSE Signal Engine — Sprint 3, Task 7
app/signals/engine.py

SignalEngine: takes a property record, runs all active signal detectors,
and writes the results to the signals table.

Design rules (from BUILD_PLAN):
  - Each signal is a callable that returns bool (pluggable).
  - Signals are stateless — recomputable from property data alone.
  - No signal depends on another signal.
  - Missing / None data → False (not flagged).
  - Supports single-property and batch modes.
  - Single-property mode: returns the dict of signal flags.
  - Batch mode: returns summary counts.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.property import Property
from app.models.signal import Signal
from app.services.address_normalizer import normalize_address
from app.services.signal_detector import detect_absentee_owner, detect_long_term_owner

log = logging.getLogger("rse.signal_engine")


# ── Signal detector adapters ──────────────────────────────────────────────────
# Each adapter takes a Property ORM object and returns a bool.
# They wrap the pure functions in signal_detector.py, handling the data
# extraction and address reconstruction from the ORM model's fields.


def _absentee_owner_detector(prop: Property) -> bool:
    """
    Adapter: detect absentee ownership from a Property ORM record.

    Reconstructs the full property address (street + city + state + zip)
    for comparison against the mailing address.  Both addresses were
    already normalized at ingestion time so we re-normalize only the
    reconstructed composite (which combines pre-normalized parts).
    """
    # A meaningful absentee comparison requires at minimum a street address.
    # Without it we cannot build a full property address and must conservatively
    # return False (insufficient data — do not flag).
    if not prop.address:
        return False

    # Build full address from stored components for apples-to-apples comparison
    # with mailing_address (which is always a full normalized address).
    parts: list[str] = [prop.address]  # normalized street (e.g. "123 MAIN ST")
    if prop.city:
        parts.append(prop.city.upper())
    if prop.state:
        parts.append(prop.state.upper())
    if prop.zip:
        parts.append(prop.zip)

    full_property_address = " ".join(parts) if parts else None
    # Re-normalize to handle any edge-cases in the composite
    normalized_full = normalize_address(full_property_address)

    return detect_absentee_owner(
        normalized_property_address=normalized_full,
        normalized_mailing_address=prop.mailing_address,  # already normalized
    )


def _long_term_owner_detector(prop: Property) -> bool:
    """
    Adapter: detect long-term ownership from a Property ORM record.

    last_sale_date on the ORM model is a Python date / datetime object.
    """
    sale_date = prop.last_sale_date
    # SQLAlchemy may return a datetime; normalize to date for the detector.
    if hasattr(sale_date, "date"):
        sale_date = sale_date.date()
    return detect_long_term_owner(sale_date)


# ── Registered signal set (Sprint 3 MVP) ─────────────────────────────────────
# Format: list of (signal_name, detector_callable)
# signal_name must match the corresponding column name on the Signal model.
# Adding a new signal: write a detector function + add an entry here.

REGISTERED_SIGNALS: list[tuple[str, Callable[[Property], bool]]] = [
    ("absentee_owner", _absentee_owner_detector),
    ("long_term_owner", _long_term_owner_detector),
]


# ── SignalEngine ──────────────────────────────────────────────────────────────

class SignalEngine:
    """
    Batch-capable signal detection engine.

    Usage (single property):
        engine = SignalEngine()
        flags = await engine.process(prop, session)
        # flags = {"absentee_owner": True, "long_term_owner": False}

    Usage (batch):
        counts = await engine.process_batch(properties, session)
        # counts = {"processed": 50, "absentee_owner": 12, "long_term_owner": 22}
    """

    def __init__(
        self,
        signals: Optional[list[tuple[str, Callable[[Property], bool]]]] = None,
    ) -> None:
        """
        Args:
            signals: Optional override of the signal registry.
                     Defaults to REGISTERED_SIGNALS.
                     Useful for testing or selectively enabling signals.
        """
        self._signals = signals if signals is not None else REGISTERED_SIGNALS

    # ── Single-property processing ────────────────────────────────────────────

    async def process(
        self,
        prop: Property,
        session: AsyncSession,
    ) -> dict[str, bool]:
        """
        Run all registered signal detectors for a single property and
        write the results to the signals table.

        Args:
            prop:    SQLAlchemy Property ORM instance.
            session: Active async database session.

        Returns:
            Dict mapping signal_name → bool for all registered signals.
        """
        flags: dict[str, bool] = {}

        for signal_name, detector in self._signals:
            try:
                flags[signal_name] = detector(prop)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "Signal %r failed for property %s: %s",
                    signal_name, prop.parcel_id, exc,
                )
                flags[signal_name] = False  # conservative fallback

        await self._upsert_signal(session, prop.id, flags)
        log.debug(
            "property=%s parcel=%s signals=%s",
            prop.id, prop.parcel_id, flags,
        )
        return flags

    # ── Batch processing ──────────────────────────────────────────────────────

    async def process_batch(
        self,
        properties: list[Property],
        session: AsyncSession,
    ) -> dict[str, int]:
        """
        Process a list of properties through all registered signal detectors.

        Each property is processed individually and the session is committed
        after all properties have been processed.

        Args:
            properties: List of SQLAlchemy Property ORM instances.
            session:    Active async database session.

        Returns:
            Summary dict:
              {
                "processed": int,               # total properties processed
                "<signal_name>": int, ...       # count of True detections per signal
              }
        """
        counts: dict[str, int] = {
            name: 0 for name, _ in self._signals
        }
        counts["processed"] = 0

        for prop in properties:
            try:
                flags = await self.process(prop, session)
                counts["processed"] += 1
                for signal_name, value in flags.items():
                    if value:
                        counts[signal_name] = counts.get(signal_name, 0) + 1
            except Exception as exc:  # noqa: BLE001
                log.error(
                    "Failed to process property %s (parcel=%s): %s",
                    prop.id, prop.parcel_id, exc,
                )
                # Continue with the next property rather than aborting the batch.

        return counts

    # ── DB helpers ────────────────────────────────────────────────────────────

    @staticmethod
    async def _upsert_signal(
        session: AsyncSession,
        property_id: uuid.UUID,
        flags: dict[str, bool],
    ) -> None:
        """
        INSERT or UPDATE a signal row for the given property_id.

        Only the signals present in `flags` are updated; placeholder signals
        (tax_delinquent, pre_foreclosure, probate, eviction, code_violation)
        are left at their existing values on UPDATE.
        """
        new_id = uuid.uuid4()

        insert_values: dict = {
            "id": new_id,
            "property_id": property_id,
            # Default all signal columns to False for new rows
            "absentee_owner": flags.get("absentee_owner", False),
            "long_term_owner": flags.get("long_term_owner", False),
            "tax_delinquent": False,
            "pre_foreclosure": False,
            "probate": False,
            "eviction": False,
            "code_violation": False,
        }

        # On conflict, only update the signals we computed + updated_at.
        # Placeholder signals retain their current value.
        update_values: dict = {
            **{k: v for k, v in flags.items()},
            "updated_at": datetime.utcnow(),
        }

        stmt = (
            pg_insert(Signal)
            .values(**insert_values)
            .on_conflict_do_update(
                index_elements=["property_id"],
                set_=update_values,
            )
        )
        await session.execute(stmt)
