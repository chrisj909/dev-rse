#!/usr/bin/env python3
"""
RSE Batch Scoring Script — Sprint 3, Task 10
backend/scripts/run_scoring.py

Runs all properties through the ScoringEngine and upserts scores to the DB.
Cron-compatible: clean exit codes, stdout logging, no interactive prompts.

Usage:
    python scripts/run_scoring.py
    python scripts/run_scoring.py --dry-run
    python scripts/run_scoring.py --batch-size 250
    python scripts/run_scoring.py --batch-size 100 --log-level DEBUG

Flags:
    --dry-run        Compute scores and log results WITHOUT writing to the DB.
    --batch-size N   Properties processed per commit batch (default: 500).
    --log-level      Logging verbosity: DEBUG | INFO | WARNING | ERROR (default: INFO).

Exit codes:
    0 — success (all properties scored, zero errors)
    1 — partial failure (one or more properties failed to score)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# ── Ensure backend/ is importable (works from repo root or backend/) ──────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPT_DIR.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.property import Property  # noqa: E402
from app.models.signal import Signal  # noqa: E402
from app.scoring.engine import ScoringEngine  # noqa: E402
from app.scoring.weights import SCORING_VERSION, calculate_score  # noqa: E402

# ── Constants ─────────────────────────────────────────────────────────────────
DEFAULT_BATCH_SIZE = 500


# ── Argument parsing ──────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RSE batch scoring — applies versioned weights to all properties.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_scoring.py
  python scripts/run_scoring.py --dry-run
  python scripts/run_scoring.py --batch-size 100 --log-level DEBUG
""",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Compute scores and log results without writing to the database.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        metavar="N",
        help=f"Number of properties processed per batch (default: {DEFAULT_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )
    return parser.parse_args()


# ── Core async logic ──────────────────────────────────────────────────────────

async def run_scoring(batch_size: int, dry_run: bool) -> dict:
    """
    Main coroutine: fetch all properties, score them, upsert results.

    Args:
        batch_size: Number of properties per commit batch.
        dry_run:    If True, compute scores but skip DB writes.

    Returns:
        Summary dict:
          {
            "total_properties": int,
            "processed":        int,
            "errors":           int,
            "rank_a":           int,
            "rank_b":           int,
            "rank_c":           int,
          }
    """
    log = logging.getLogger("rse.run_scoring")
    engine = ScoringEngine(scoring_version=SCORING_VERSION)

    summary: dict[str, int] = {
        "total_properties": 0,
        "processed": 0,
        "errors": 0,
        "rank_a": 0,
        "rank_b": 0,
        "rank_c": 0,
    }

    async with AsyncSessionLocal() as session:
        # Load all properties
        result = await session.execute(select(Property))
        all_properties = list(result.scalars().all())
        total = len(all_properties)
        summary["total_properties"] = total

        log.info("Found %d properties to score (version=%s)", total, SCORING_VERSION)

        if total == 0:
            log.warning("No properties found — nothing to score.")
            return summary

        if dry_run:
            log.info("[DRY RUN] Computing scores without writing to database…")
            # Compute scores using the pure function — no DB writes
            for prop in all_properties:
                try:
                    sig_result = await session.execute(
                        select(Signal).where(Signal.property_id == prop.id)
                    )
                    signal_row = sig_result.scalar_one_or_none()
                    if signal_row:
                        flags = {
                            "absentee_owner":  signal_row.absentee_owner,
                            "long_term_owner": signal_row.long_term_owner,
                            "tax_delinquent":  signal_row.tax_delinquent,
                            "pre_foreclosure": signal_row.pre_foreclosure,
                            "probate":         signal_row.probate,
                            "code_violation":  signal_row.code_violation,
                        }
                    else:
                        flags = {}

                    score_val, rank, reasons = calculate_score(flags)
                    log.debug(
                        "[DRY RUN] parcel=%-20s score=%3d rank=%s reasons=%s",
                        getattr(prop, "parcel_id", "?"),
                        score_val,
                        rank,
                        reasons,
                    )
                    summary["processed"] += 1
                    summary[f"rank_{rank.lower()}"] += 1
                except Exception as exc:  # noqa: BLE001
                    log.error("[DRY RUN] Failed to compute score for %s: %s", prop.id, exc)
                    summary["errors"] += 1

            log.info("[DRY RUN] No changes written to database.")
            return summary

        # Live run — process in batches with a commit after each
        offset = 0
        batch_num = 0
        while offset < total:
            batch = all_properties[offset: offset + batch_size]
            if not batch:
                break

            batch_num += 1
            log.info(
                "Scoring batch %d: properties %d–%d of %d…",
                batch_num,
                offset + 1,
                min(offset + batch_size, total),
                total,
            )

            try:
                counts = await engine.score_batch(batch, session)
                await session.commit()

                summary["processed"] += counts["processed"]
                summary["errors"] += counts.get("errors", 0)
                summary["rank_a"] += counts.get("rank_a", 0)
                summary["rank_b"] += counts.get("rank_b", 0)
                summary["rank_c"] += counts.get("rank_c", 0)

                log.info(
                    "  Batch %d done — processed=%d errors=%d A=%d B=%d C=%d",
                    batch_num,
                    counts["processed"],
                    counts.get("errors", 0),
                    counts.get("rank_a", 0),
                    counts.get("rank_b", 0),
                    counts.get("rank_c", 0),
                )
            except Exception as exc:  # noqa: BLE001
                log.error("Batch %d failed entirely: %s", batch_num, exc)
                await session.rollback()
                summary["errors"] += len(batch)

            offset += batch_size

    return summary


# ── CLI entrypoint ────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    log = logging.getLogger("rse.run_scoring")
    log.info("=" * 60)
    log.info("RSE Batch Scoring Job")
    log.info("Scoring version : %s", SCORING_VERSION)
    log.info("Batch size      : %d", args.batch_size)
    log.info("Dry run         : %s", args.dry_run)
    log.info("=" * 60)

    summary = asyncio.run(run_scoring(args.batch_size, args.dry_run))

    log.info("-" * 60)
    log.info("Scoring complete.")
    log.info("  Total properties : %d", summary["total_properties"])
    log.info("  Processed        : %d", summary["processed"])
    log.info("  Errors           : %d", summary["errors"])
    log.info("  Rank A (score≥25): %d", summary["rank_a"])
    log.info("  Rank B (15–24)   : %d", summary["rank_b"])
    log.info("  Rank C (<15)     : %d", summary["rank_c"])
    log.info("=" * 60)

    # Exit 1 if any errors occurred (useful for cron monitoring / alerting)
    if summary["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
