#!/usr/bin/env python3
"""
RSE Property Ingestion Script — Sprint 2, Task 4
backend/scripts/ingest_properties.py

Usage:
    python scripts/ingest_properties.py --csv data/sample_properties.csv
    python scripts/ingest_properties.py --csv data/sample_properties.csv --dry-run

What it does:
  1. Reads a CSV file of property records.
  2. Normalizes raw addresses via the address_normalizer utility.
    3. Upserts records into the `properties` table (dedupe key: county + parcel_id).
  4. Runs absentee_owner + long_term_owner detection via signal_detector.
  5. Upserts signal rows for each property.
  6. Logs: inserted count, updated count, skipped (error) count.

Design rules followed:
    - county + parcel_id is the primary dedupe key — never address.
  - Always store raw + normalized addresses side by side.
  - Signals are stateless and recomputable.
  - Script is cron-compatible: clean exit codes, stdout logging, no prompts.
"""

import argparse
import asyncio
import csv
import logging
import os
import sys
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ── Path setup ────────────────────────────────────────────────────────────────
# Allow running from repo root OR from backend/ directory.
_SCRIPT_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPT_DIR.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# ── Third-party / project imports (after path fix) ───────────────────────────
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.property import Property
from app.models.signal import Signal
from app.services.address_normalizer import normalize_address
from app.services.signal_detector import detect_property_signals

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("rse.ingest")

# ── CSV column definitions ────────────────────────────────────────────────────
# Maps CSV header names to internal field names.
# All fields are optional except parcel_id.
REQUIRED_FIELDS = {"parcel_id"}
OPTIONAL_FIELDS = {
    "county",
    "raw_address",
    "city",
    "state",
    "zip",
    "owner_name",
    "raw_mailing_address",
    "last_sale_date",
    "assessed_value",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(value: str) -> Optional[date]:
    """Parse an ISO date string (YYYY-MM-DD). Returns None on failure."""
    if not value or not value.strip():
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    log.warning("  Could not parse date %r — skipping field", value)
    return None


def _parse_decimal(value: str) -> Optional[float]:
    """Parse a numeric string. Returns None on failure."""
    if not value or not value.strip():
        return None
    try:
        return float(value.strip().replace(",", "").replace("$", ""))
    except ValueError:
        log.warning("  Could not parse numeric %r — skipping field", value)
        return None


def _build_full_address(street: Optional[str], city: Optional[str], state: str, zip_code: Optional[str]) -> Optional[str]:
    """
    Construct a full address string from components for comparison purposes.
    County data typically stores the property address as just the street, but
    mailing addresses are always full addresses. We build a full property address
    so both can be normalized and compared on equal footing.

    Example: "124 Oak Street" + "Hoover" + "AL" + "35244"
             → "124 Oak Street Hoover AL 35244"
    """
    if not street or not street.strip():
        return None
    parts = [street.strip()]
    if city and city.strip():
        parts.append(city.strip())
    if state and state.strip():
        parts.append(state.strip())
    if zip_code and zip_code.strip():
        parts.append(zip_code.strip())
    return " ".join(parts)


def _row_to_property_data(row: dict, row_num: int) -> Optional[dict]:
    """
    Convert a CSV row dict to a flat dict ready for the properties table.
    Returns None if the row is invalid (missing required fields).
    """
    parcel_id = row.get("parcel_id", "").strip()
    if not parcel_id:
        log.warning("Row %d: missing parcel_id — skipping", row_num)
        return None

    raw_address = row.get("raw_address", "").strip() or None
    raw_mailing = row.get("raw_mailing_address", "").strip() or None
    city = row.get("city", "").strip() or None
    state = row.get("state", "AL").strip() or "AL"
    zip_code = row.get("zip", "").strip() or None

    # Build a full property address for signal comparison.
    # County data often stores only the street in raw_address, but mailing
    # addresses include city/state/zip. Without constructing a full property
    # address, owner-occupied properties would be incorrectly flagged as absentee.
    full_property_address = _build_full_address(raw_address, city, state, zip_code)

    return {
        "parcel_id": parcel_id,
        "raw_address": raw_address,
        "address": normalize_address(raw_address),          # street only (for display)
        "full_address": normalize_address(full_property_address),  # full (for comparison)
        "city": city,
        "state": state,
        "zip": zip_code,
        "owner_name": row.get("owner_name", "").strip() or None,
        "raw_mailing_address": raw_mailing,
        "mailing_address": normalize_address(raw_mailing),
        "last_sale_date": _parse_date(row.get("last_sale_date", "")),
        "assessed_value": _parse_decimal(row.get("assessed_value", "")),
    }


# ── Core async logic ──────────────────────────────────────────────────────────

async def ingest_csv(csv_path: Path, dry_run: bool = False) -> dict:
    """
    Main ingestion coroutine.

    Returns a summary dict:
        {"inserted": int, "updated": int, "skipped": int, "total_rows": int}
    """
    counts = {"inserted": 0, "updated": 0, "skipped": 0, "total_rows": 0}

    if not csv_path.exists():
        log.error("CSV file not found: %s", csv_path)
        sys.exit(1)

    # Read all rows up front so we can report total before DB work
    rows: list[dict] = []
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                log.error("CSV file appears to be empty or has no header row.")
                sys.exit(1)

            # Validate required columns exist
            missing_cols = REQUIRED_FIELDS - set(reader.fieldnames)
            if missing_cols:
                log.error("CSV is missing required columns: %s", missing_cols)
                sys.exit(1)

            rows = list(reader)
    except UnicodeDecodeError:
        # Retry with latin-1 fallback for files from Windows sources
        log.warning("UTF-8 decode failed, retrying with latin-1 encoding…")
        with open(csv_path, newline="", encoding="latin-1") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)

    counts["total_rows"] = len(rows)
    log.info("Read %d rows from %s", len(rows), csv_path)

    if dry_run:
        log.info("[DRY RUN] Parsing rows without writing to database…")

    async with AsyncSessionLocal() as session:
        for row_num, raw_row in enumerate(rows, start=2):  # start=2: row 1 is header
            prop_data = _row_to_property_data(raw_row, row_num)
            if prop_data is None:
                counts["skipped"] += 1
                continue

            if dry_run:
                log.info(
                    "  [DRY RUN] Row %d: parcel_id=%s address=%s",
                    row_num,
                    prop_data["parcel_id"],
                    prop_data["address"],
                )
                counts["inserted"] += 1  # count as would-be inserts for dry run
                continue

            try:
                # ── Upsert property ───────────────────────────────────────────
                # Use PostgreSQL INSERT … ON CONFLICT DO UPDATE.
                # parcel_id is the dedupe key.
                # Strip full_address (comparison-only field, not a DB column).
                db_prop_data = {k: v for k, v in prop_data.items() if k != "full_address"}
                prop_id = await _upsert_property(session, db_prop_data)
                was_new = prop_id[1]  # (uuid, is_new_row)
                property_uuid = prop_id[0]

                if was_new:
                    counts["inserted"] += 1
                    log.debug(
                        "  INSERTED parcel_id=%s → %s", prop_data["parcel_id"], property_uuid
                    )
                else:
                    counts["updated"] += 1
                    log.debug(
                        "  UPDATED  parcel_id=%s → %s", prop_data["parcel_id"], property_uuid
                    )

                # ── Detect + upsert signals ───────────────────────────────────
                # Use full_address (street + city + state + zip) for absentee
                # comparison so it's on equal footing with the mailing address
                # which always includes city/state/zip.
                signals = detect_property_signals(
                    normalized_property_address=prop_data["full_address"],
                    normalized_mailing_address=prop_data["mailing_address"],
                    last_sale_date=prop_data["last_sale_date"],
                )
                await _upsert_signal(session, property_uuid, signals)

            except Exception as exc:  # noqa: BLE001
                log.error(
                    "  ERROR on row %d (parcel_id=%s): %s",
                    row_num,
                    prop_data.get("parcel_id", "?"),
                    exc,
                )
                counts["skipped"] += 1
                await session.rollback()
                continue

        if not dry_run:
            await session.commit()

    return counts


async def _upsert_property(session, prop_data: dict) -> tuple[uuid.UUID, bool]:
    """
    INSERT or UPDATE a property row. Returns (uuid, is_new_row).

    Uses PostgreSQL ON CONFLICT DO UPDATE to handle the dedupe.
    We detect whether it was an insert or update by checking if
    `created_at == updated_at` after the upsert (server-side default comparison).
    """
    new_id = uuid.uuid4()

    insert_values = {
        "id": new_id,
        **prop_data,
    }

    prop_data.setdefault("county", "shelby")

    # Columns to update on conflict (exclude id, key columns, created_at)
    update_values = {
        k: v
        for k, v in prop_data.items()
        if k not in ("county", "parcel_id")
    }
    # Always bump updated_at on conflict
    update_values["updated_at"] = datetime.utcnow()

    stmt = (
        pg_insert(Property)
        .values(**insert_values)
        .on_conflict_do_update(
            index_elements=["county", "parcel_id"],
            set_=update_values,
        )
        .returning(Property.id, Property.created_at, Property.updated_at)
    )

    result = await session.execute(stmt)
    row = result.fetchone()

    property_uuid = row[0]
    created_at = row[1]
    updated_at = row[2]

    # is_new_row: if created_at ~= updated_at, it's a fresh insert.
    # (Both default to now() server-side; on update we set updated_at explicitly.)
    is_new = property_uuid == new_id  # Simpler: if the DB returned our new UUID it's an insert
    return (property_uuid, is_new)


async def _upsert_signal(
    session,
    property_id: uuid.UUID,
    signal_flags: dict[str, bool],
) -> None:
    """
    INSERT or UPDATE a signal row for the given property_id.
    Only writes absentee_owner + long_term_owner in Sprint 2.
    Placeholder signals remain at their existing/default values.
    """
    new_signal_id = uuid.uuid4()

    insert_values = {
        "id": new_signal_id,
        "property_id": property_id,
        "absentee_owner": signal_flags.get("absentee_owner", False),
        "long_term_owner": signal_flags.get("long_term_owner", False),
        # Placeholder signals default to False — not touched here
        "tax_delinquent": False,
        "pre_foreclosure": False,
        "probate": False,
        "eviction": False,
        "code_violation": False,
    }

    update_values = {
        "absentee_owner": signal_flags.get("absentee_owner", False),
        "long_term_owner": signal_flags.get("long_term_owner", False),
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


# ── CLI entrypoint ────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest property CSV data into the RSE database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/ingest_properties.py --csv data/sample_properties.csv
  python scripts/ingest_properties.py --csv data/sample_properties.csv --dry-run
  python scripts/ingest_properties.py --csv /path/to/file.csv --log-level DEBUG
""",
    )
    parser.add_argument(
        "--csv",
        required=True,
        metavar="PATH",
        help="Path to the CSV file to ingest.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Parse and validate the CSV without writing to the database.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logging.getLogger().setLevel(args.log_level)

    csv_path = Path(args.csv)

    log.info("=" * 60)
    log.info("RSE Property Ingestion")
    log.info("CSV: %s", csv_path.resolve())
    log.info("Dry run: %s", args.dry_run)
    log.info("Database: %s", settings.database_url)
    log.info("=" * 60)

    counts = asyncio.run(ingest_csv(csv_path, dry_run=args.dry_run))

    log.info("-" * 60)
    log.info("Ingestion complete.")
    log.info("  Total rows read : %d", counts["total_rows"])
    log.info("  Inserted        : %d", counts["inserted"])
    log.info("  Updated         : %d", counts["updated"])
    log.info("  Skipped (errors): %d", counts["skipped"])
    log.info("=" * 60)

    # Exit code 1 if there were any skipped rows (useful for monitoring)
    if counts["skipped"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
