"""
Birmingham 311 Code Violation Scraper
app/scrapers/birmingham_311_scraper.py

Fetches code violation cases from the Birmingham 311 Open Data portal (CKAN API).
Returns a set of normalized street addresses that have at least one active violation.

Data source:
  API:         https://data.birminghamal.gov/api/3/action/datastore_search
  Resource ID: 9d55626a-afb2-4473-a084-cb70e721af23
  Fields:      Case Number, Case Type, Street Number, Street Name,
               Street Type, Street Direction, Created On

Only covers Birmingham, AL — Jefferson county properties only.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from app.services.address_normalizer import normalize_address

log = logging.getLogger("rse.birmingham_311")

CKAN_URL = "https://data.birminghamal.gov/api/3/action/datastore_search"
RESOURCE_ID = "9d55626a-afb2-4473-a084-cb70e721af23"
PAGE_SIZE = 1000

# Case types that represent actionable code violations
VIOLATION_CASE_TYPES: frozenset[str] = frozenset({
    "Overgrown Vacant Lot",
    "Dilapidated House or Building",
    "Burned Structure More Than 50%",
    "Illegal Dumping",
    "Overgrown/Junky Yard Inop Vehicle Occupied",
    "Substandard Building",
    "Unsafe Structure",
})


def _build_address(record: dict) -> Optional[str]:
    """Reconstruct a street address string from separate 311 record fields."""
    number = str(record.get("Street Number") or "").strip()
    direction = str(record.get("Street Direction") or "").strip()
    name = str(record.get("Street Name") or "").strip()
    suffix = str(record.get("Street Type") or "").strip()

    if not number or not name:
        return None

    parts = [p for p in [number, direction, name, suffix] if p]
    return " ".join(parts)


async def fetch_code_violation_addresses(
    resource_id: str = RESOURCE_ID,
    case_types: Optional[frozenset[str]] = None,
    http_client: Optional[httpx.AsyncClient] = None,
) -> set[str]:
    """
    Fetch all code violation addresses from the Birmingham 311 CKAN API.

    Paginates through all records, filters to `case_types`, normalizes the
    reconstructed street address, and returns a set of normalized strings.

    Args:
        resource_id:  CKAN resource ID (overridable for testing).
        case_types:   Set of case type strings to treat as violations.
                      Defaults to VIOLATION_CASE_TYPES.
        http_client:  Optional pre-built httpx.AsyncClient (for testing/reuse).

    Returns:
        Set of normalized street addresses (no city/state) with >= 1 violation.
    """
    if case_types is None:
        case_types = VIOLATION_CASE_TYPES

    violation_addresses: set[str] = set()
    offset = 0

    async def _fetch_page(client: httpx.AsyncClient, off: int) -> list[dict]:
        resp = await client.get(
            CKAN_URL,
            params={"resource_id": resource_id, "limit": PAGE_SIZE, "offset": off},
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"CKAN API returned success=false at offset {off}")
        return data.get("result", {}).get("records", [])

    async def _run(client: httpx.AsyncClient) -> None:
        nonlocal offset
        while True:
            try:
                records = await _fetch_page(client, offset)
            except Exception as exc:
                log.error("Birmingham 311 fetch error at offset %d: %s", offset, exc)
                break

            if not records:
                break

            for record in records:
                case_type = str(record.get("Case Type") or "").strip()
                if case_type not in case_types:
                    continue
                addr = _build_address(record)
                if not addr:
                    continue
                normalized = normalize_address(addr)
                if normalized:
                    violation_addresses.add(normalized)

            offset += len(records)
            if len(records) < PAGE_SIZE:
                break

            await asyncio.sleep(0.05)

    if http_client is not None:
        await _run(http_client)
    else:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await _run(client)

    log.info(
        "Birmingham 311: fetched %d unique violation addresses (offset=%d)",
        len(violation_addresses),
        offset,
    )
    return violation_addresses
