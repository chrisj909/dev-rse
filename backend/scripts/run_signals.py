#!/usr/bin/env python3
"""
RSE Batch Signal Processing Script — Sprint 3, Task 8
backend/scripts/run_signals.py

Processes all properties in the database through the SignalEngine and
writes/updates signal flags to the signals table.

Usage:
    python scripts/run_signals.py
    python scripts/run_signals.py --batch-size 100
    python scripts/run_signals.py --dry-run
    python scripts/run_signals.py --log-level DEBUG

Cron-compatible:
    - Clean exit codes (0 = success, 1 = partial failure)
    - All output to stdout/stderr (no interactive prompts)
    - Designed to be triggered by Vercel cron or system cron

Vercel cron endpoint (wired in vercel.json):
    GET /api/cron/run-signals
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

# ── Path setup ─────────────────────────────────────────────────────────────────
# Allow running from repo root OR from backend/ directory.
_SCRIPT_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPT_DIR.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.property import Property  # noqa: E402
from app.signals.engine import SignalEngine  # noqa: E402

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("rse.run_signals")

# ── Default batch size ─────────────────────────────────────────────────────────
DEFAULT_BATCH_SIZE = 500


# ── Core async logic ───────────────────────────────────────────────────────────

async def run_signals(batch_size: int = DEFAULT_BATCH_SIZE, dry_run: bool = False) -> dict:
    """
    Main coroutine: fetches all properties and processes them through SignalEngine.

    Args:
        batch_size: Number of properties to load per DB query.
        dry_run:    If True, log what would be processed without writing to DB.

    Returns:
        Summary dict:
          {
            "total_properties": int,
            "processed": int,
            "errors": int,
            "<signal_name>": int,  ...
          }
    """
    engine = SignalEngine()
    summary: dict[str, int] = {
        "total_properties": 0,
        "processed": 0,
        "errors": 0,
        "absentee_owner": 0,
        "long_term_owner": 0,
    }

    if dry_run:
        log.info("[DRY RUN] Counting properties without processing signals…")

    async with AsyncSessionLocal() as session:
        # Count total properties first (for progress logging)
        count_stmt = select(Property)
        result = await session.execute(count_stmt)
        all_properties = result.scalars().all()
        total = len(all_properties)
        summary["total_properties"] = total

        log.info("Found %d properties to process.", total)

        if dry_run:
            log.info("[DRY RUN] Would process %d properties.", total)
            log.info("[DRY RUN] No changes written to database.")
            summary["processed"] = total
            return summary

        # Process in batches
        offset = 0
        while offset < total:
            batch = all_properties[offset : offset + batch_size]
            if not batch:
                break

            log.info(
                "Processing batch %d–%d of %d…",
                offset + 1, min(offset + batch_size, total), total,
            )

            try:
                counts = await engine.process_batch(batch, session)
                await session.commit()

                summary["processed"] += counts.get("processed", 0)
                summary["absentee_owner"] += counts.get("absentee_owner", 0)
                summary["long_term_owner"] += counts.get("long_term_owner", 0)

                log.info(
                    "  Batch done — processed=%d, absentee=%d, long_term=%d",
                    counts.get("processed", 0),
                    counts.get("absentee_owner", 0),
                    counts.get("long_term_owner", 0),
                )
            except Exception as exc:  # noqa: BLE001
                log.error("Batch %d–%d failed: %s", offset + 1, offset + batch_size, exc)
                await session.rollback()
                summary["errors"] += len(batch)

            offset += batch_size

    return summary


# ── CLI entrypoint ─────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run signal detection on all properties in the RSE database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_signals.py
  python scripts/run_signals.py --batch-size 250 --log-level DEBUG
  python scripts/run_signals.py --dry-run
""",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        metavar="N",
        help=f"Number of properties per processing batch (default: {DEFAULT_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Count properties without writing signal updates to the database.",
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

    log.info("=" * 60)
    log.info("RSE Batch Signal Processing")
    log.info("Batch size : %d", args.batch_size)
    log.info("Dry run    : %s", args.dry_run)
    log.info("=" * 60)

    summary = asyncio.run(run_signals(args.batch_size, args.dry_run))

    log.info("-" * 60)
    log.info("Signal run complete.")
    log.info("  Total properties : %d", summary["total_properties"])
    log.info("  Processed        : %d", summary["processed"])
    log.info("  Errors           : %d", summary["errors"])
    log.info("  absentee_owner   : %d", summary["absentee_owner"])
    log.info("  long_term_owner  : %d", summary["long_term_owner"])
    log.info("=" * 60)

    # Exit 1 if any errors occurred (useful for cron monitoring)
    if summary["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
