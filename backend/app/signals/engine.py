"""
RSE Signal Engine — Sprint 3 (Task 7), refactored Sprint 7 (Task 15)
app/signals/engine.py

SignalEngine: takes a property record, runs all registered signal detectors,
and writes the results to the signals table.

Design rules (from BUILD_PLAN):
  - Each signal is a callable: (Property) -> bool  (pluggable).
  - Signals are stateless — recomputable from property data alone.
  - No signal depends on another signal.
  - Missing / None data → False (not flagged).
  - Supports single-property and batch modes.

Sprint 7 — Pluggable registry:
  - Class-level registry via SignalEngine.register(name, fn).
  - SignalEngine.deregister(name) removes a signal by name.
  - SignalEngine.registered_signals() returns the current registry snapshot.
  - Four new stub signals registered at module load time:
      tax_delinquent, probate, code_violation, pre_foreclosure
    All stubs return False until their data ingestion pipelines are built.
  - Instance can still receive an explicit signals list (for testing / overrides).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, ClassVar, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.property import Property
from app.models.signal import Signal
from app.services.address_normalizer import normalize_address
from app.services.signal_detector import (
    detect_absentee_owner,
    detect_corporate_owner,
    detect_long_term_owner,
    detect_out_of_state_owner,
)

log = logging.getLogger("rse.signal_engine")

# Type alias for a signal detector callable.
SignalFn = Callable[[Property], bool]


# ── Built-in detector adapters ────────────────────────────────────────────────
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
    if not prop.address:
        return False

    parts: list[str] = [prop.address]
    if prop.city:
        parts.append(prop.city.upper())
    if prop.state:
        parts.append(prop.state.upper())
    if prop.zip:
        parts.append(prop.zip)

    full_property_address = " ".join(parts) if parts else None
    normalized_full = normalize_address(full_property_address)

    return detect_absentee_owner(
        normalized_property_address=normalized_full,
        normalized_mailing_address=prop.mailing_address,
    )


def _long_term_owner_detector(prop: Property) -> bool:
    """
    Adapter: detect long-term ownership from a Property ORM record.

    last_sale_date on the ORM model is a Python date / datetime object.
    """
    sale_date = prop.last_sale_date
    if hasattr(sale_date, "date"):
        sale_date = sale_date.date()
    return detect_long_term_owner(sale_date)


def _out_of_state_owner_detector(prop: Property) -> bool:
    """Adapter: detect out-of-state owners from mailing address state suffix."""
    return detect_out_of_state_owner(
        normalized_mailing_address=prop.mailing_address,
        property_state=prop.state,
    )


def _corporate_owner_detector(prop: Property) -> bool:
    """Adapter: detect owner names that look like corporate or trust entities."""
    return detect_corporate_owner(prop.owner_name)


# ── Placeholder / stub detectors ──────────────────────────────────────────────
# These return False until their real data ingestion pipelines are wired up.
# tax_delinquent is written directly by TaxDelinquencyService; the engine
# stub here is a read-through for future re-compute flows.


def _tax_delinquent_stub(prop: Property) -> bool:  # pragma: no cover
    """
    Stub: tax delinquency signal.

    Real value is ingested via TaxDelinquencyService (scripts/ingest_tax_delinquency.py).
    Returns False here; the signal engine defers to the stored DB value written
    by that service rather than recomputing from property fields.
    """
    return False


def _probate_stub(prop: Property) -> bool:  # pragma: no cover
    """
    Stub: probate filing signal.

    Will be powered by Shelby County Probate Office data (source 3.5).
    Returns False until that ingestion pipeline is built.
    """
    return False


def _code_violation_stub(prop: Property) -> bool:  # pragma: no cover
    """
    Stub: code violation signal.

    Will be powered by City Open Data / 311 records (source 3.6).
    Returns False until that ingestion pipeline is built.
    """
    return False


def _pre_foreclosure_stub(prop: Property) -> bool:  # pragma: no cover
    """
    Stub: pre-foreclosure signal.

    Will be powered by Alabama Court System (Alacourt) data (source 3.4).
    Returns False until that ingestion pipeline is built.
    """
    return False


def _eviction_stub(prop: Property) -> bool:  # pragma: no cover
    """Stub: eviction filing signal until a public eviction data source is wired."""
    return False


# ── SignalEngine ──────────────────────────────────────────────────────────────

class SignalEngine:
    """
    Batch-capable signal detection engine with a pluggable class-level registry.

    Class-level registry (shared across all instances unless overridden):
        SignalEngine.register("my_signal", my_detector_fn)
        SignalEngine.deregister("my_signal")
        SignalEngine.registered_signals()  → list[tuple[str, SignalFn]]

    Instance-level override (for testing / selective runs):
        engine = SignalEngine(signals=[("absentee_owner", fn)])

    Usage (single property):
        engine = SignalEngine()
        flags = await engine.process(prop, session)
        # {"absentee_owner": True, "long_term_owner": False, ...}

    Usage (batch):
        counts = await engine.process_batch(properties, session)
        # {"processed": 50, "absentee_owner": 12, ...}
    """

    # ── Class-level registry ──────────────────────────────────────────────────
    # OrderedDict behaviour: signals are run in registration order.
    # Keys are signal names (must match Signal ORM column names).
    _registry: ClassVar[dict[str, SignalFn]] = {}

    @classmethod
    def register(cls, name: str, fn: SignalFn) -> None:
        """
        Register a signal detector at class level.

        Args:
            name: Signal name. Must match the corresponding Signal ORM column.
            fn:   Callable (Property) -> bool.

        If a signal with the same name is already registered it is replaced.
        """
        if not callable(fn):
            raise TypeError(f"Signal detector for {name!r} must be callable, got {type(fn)!r}")
        cls._registry[name] = fn
        log.debug("Registered signal: %r", name)

    @classmethod
    def deregister(cls, name: str) -> None:
        """
        Remove a registered signal by name.

        Args:
            name: Signal name to remove.

        Raises:
            KeyError: if the signal name is not registered.
        """
        if name not in cls._registry:
            raise KeyError(f"Signal {name!r} is not registered")
        del cls._registry[name]
        log.debug("Deregistered signal: %r", name)

    @classmethod
    def registered_signals(cls) -> list[tuple[str, SignalFn]]:
        """Return a snapshot of the current registry as (name, fn) pairs."""
        return list(cls._registry.items())

    # ── Instance init ─────────────────────────────────────────────────────────

    def __init__(
        self,
        signals: Optional[list[tuple[str, SignalFn]]] = None,
    ) -> None:
        """
        Args:
            signals: Optional explicit signal list.
                     If provided, this instance uses it instead of the
                     class-level registry. Useful for testing.
        """
        self._signals_override = signals

    @property
    def _signals(self) -> list[tuple[str, SignalFn]]:
        """Return the effective signal list for this instance."""
        if self._signals_override is not None:
            return self._signals_override
        return self.registered_signals()

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
                flags[signal_name] = False

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

        Args:
            properties: List of SQLAlchemy Property ORM instances.
            session:    Active async database session.

        Returns:
            Summary dict: {"processed": N, "<signal_name>": N, ...}
        """
        counts: dict[str, int] = {name: 0 for name, _ in self._signals}
        counts["processed"] = 0

        for prop in properties:
            try:
                async with session.begin_nested():
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

        Only the signals present in `flags` are updated on conflict;
        any signal column not in `flags` retains its existing value.
        """
        new_id = uuid.uuid4()

        insert_values: dict = {
            "id": new_id,
            "property_id": property_id,
            "absentee_owner": flags.get("absentee_owner", False),
            "long_term_owner": flags.get("long_term_owner", False),
            "out_of_state_owner": flags.get("out_of_state_owner", False),
            "corporate_owner": flags.get("corporate_owner", False),
            "tax_delinquent": flags.get("tax_delinquent", False),
            "pre_foreclosure": flags.get("pre_foreclosure", False),
            "probate": flags.get("probate", False),
            "eviction": flags.get("eviction", False),
            "code_violation": flags.get("code_violation", False),
        }

        update_values: dict = {
            **{k: v for k, v in flags.items()},
            "updated_at": datetime.now(tz=timezone.utc),
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


# ── Default signal registry (populated at module load) ────────────────────────
# Registration order determines execution order during processing.

SignalEngine.register("absentee_owner", _absentee_owner_detector)
SignalEngine.register("long_term_owner", _long_term_owner_detector)
SignalEngine.register("out_of_state_owner", _out_of_state_owner_detector)
SignalEngine.register("corporate_owner", _corporate_owner_detector)
SignalEngine.register("tax_delinquent", _tax_delinquent_stub)
SignalEngine.register("probate", _probate_stub)
SignalEngine.register("eviction", _eviction_stub)
SignalEngine.register("code_violation", _code_violation_stub)
SignalEngine.register("pre_foreclosure", _pre_foreclosure_stub)
