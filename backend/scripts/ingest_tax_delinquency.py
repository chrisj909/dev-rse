"""
RSE Tax Delinquency Ingestion Script — Sprint 7, Task 14
scripts/ingest_tax_delinquency.py

CLI that reads a CSV of tax delinquency records and updates the signals table.

Expected CSV columns:
    parcel_id       — string, matches properties.parcel_id
    is_delinquent   — "true"/"false" or "1"/"0"

Usage:
    python scripts/ingest_tax_delinquency.py data/tax_delinquent.csv
    python scripts/ingest_tax_delinquency.py data/tax_delinquent.csv --dry-run
    python scripts/ingest_tax_delinquency.py data/tax_delinquent.csv --log-level DEBUG
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import sys
import uuid
from pathlib import Path

# Ensure the backend package is importable when run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.config import settings  # noqa: F401 — loads .env
from app.db.session import async_session_factory
from app.models.property import Property
from app.services.tax_delinquency import TaxDelinquencyService

log = logging.getLogger("rse.ingest_tax_delinquency")


# ── CSV parsing helpers ───────────────────────────────────────────────────────

def _parse_bool(value: str) -> bool:
    """Parse a CSV boolean cell to Python bool."""
    return value.strip().lower() in ("true", "1", "yes", "t")


def _load_csv(path: Path) -> list[dict]:
    """Read and validate CSV rows, returning list of raw dicts."""
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        required = {"parcel_id", "is_delinquent"}
        if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
            missing = required - set(reader.fieldnames or [])
            raise ValueError(f"CSV missing required columns: {missing}")
        for i, row in enumerate(reader, start=2):  # row 1 = header
            parcel_id = row.get("parcel_id", "").strip()
            is_delinquent_raw = row.get("is_delinquent", "").strip()
            if not parcel_id:
                log.warning("Row %d: empty parcel_id — skipping", i)
                continue
            rows.append({
                "parcel_id": parcel_id,
                "is_delinquent": _parse_bool(is_delinquent_raw),
            })
    return rows


# ── Main ingestion logic ──────────────────────────────────────────────────────

async def run(csv_path: Path, dry_run: bool = False) -> None:
    rows = _load_csv(csv_path)
    log.info("Loaded %d rows from %s", len(rows), csv_path)

    if dry_run:
        log.info("[DRY RUN] Would process %d records — no DB writes", len(rows))
        for row in rows:
            log.info("  parcel_id=%s is_delinquent=%s", row["parcel_id"], row["is_delinquent"])
        return

    service = TaxDelinquencyService()
    counts = {"processed": 0, "updated": 0, "not_found": 0, "error": 0}

    async with async_session_factory() as session:
        for row in rows:
            parcel_id = row["parcel_id"]
            is_delinquent = row["is_delinquent"]

            # Resolve parcel_id → UUID
            result = await session.execute(
                select(Property.id).where(Property.parcel_id == parcel_id)
            )
            property_id = result.scalar_one_or_none()

            if property_id is None:
                log.warning("parcel_id=%s not found in properties table — skipping", parcel_id)
                counts["not_found"] += 1
                counts["processed"] += 1
                continue

            try:
                wrote = await service.ingest_tax_delinquency(
                    property_id=property_id,
                    is_delinquent=is_delinquent,
                    session=session,
                )
                counts["processed"] += 1
                if wrote:
                    counts["updated"] += 1
            except Exception as exc:
                log.error("Error processing parcel_id=%s: %s", parcel_id, exc)
                counts["error"] += 1
                counts["processed"] += 1

        await session.commit()

    log.info(
        "Done — processed=%d updated=%d not_found=%d error=%d",
        counts["processed"],
        counts["updated"],
        counts["not_found"],
        counts["error"],
    )
    if counts["error"] > 0:
        sys.exit(1)


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest tax delinquency flags from CSV into the RSE signals table."
    )
    parser.add_argument(
        "csv_file",
        type=Path,
        help="Path to CSV file with columns: parcel_id, is_delinquent",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate the CSV without writing to the database.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not args.csv_file.exists():
        log.error("CSV file not found: %s", args.csv_file)
        sys.exit(1)

    asyncio.run(run(csv_path=args.csv_file, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
