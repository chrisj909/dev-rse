"""County-aware parcel and overlay scrapers."""
from datetime import datetime
from typing import TypedDict

from .arcgis_scraper import ArcGISScraper
from .govease_scraper import GovEaseScraper

SUPPORTED_COUNTIES = ("shelby", "jefferson")


class ScraperRunResult(TypedDict):
    records: list[dict]
    primary_fetched: int


def _resolve_counties(county: str | None) -> list[str]:
    normalized = (county or "all").strip().lower()
    if normalized == "all":
        return list(SUPPORTED_COUNTIES)
    if normalized not in SUPPORTED_COUNTIES:
        raise ValueError(f"Unsupported county: {county}")
    return [normalized]


async def run_all_scrapers(
    limit: int | None = None,
    county: str = "all",
    updated_since: datetime | None = None,
    start_offset: int = 0,
) -> list[dict]:
    result = await run_all_scrapers_with_metadata(
        limit=limit,
        county=county,
        updated_since=updated_since,
        start_offset=start_offset,
    )
    return result["records"]


async def run_all_scrapers_with_metadata(
    limit: int | None = None,
    county: str = "all",
    updated_since: datetime | None = None,
    start_offset: int = 0,
) -> ScraperRunResult:
    """Run county scrapers and merge results by (county, parcel_id)."""
    results: dict[tuple[str, str], dict] = {}
    counties = _resolve_counties(county)
    primary_fetched = 0

    if start_offset and len(counties) != 1:
        raise ValueError("start_offset is only supported for single-county ingest runs")

    for county_name in counties:
        arcgis = ArcGISScraper(county=county_name)
        arcgis_records = await arcgis.fetch_all(
            limit=limit,
            updated_since=updated_since,
            start_offset=start_offset,
        )
        primary_fetched += len(arcgis_records)
        for record in arcgis_records:
            results[(record["county"], record["parcel_id"])] = record

        if start_offset == 0:
            govease = GovEaseScraper(county=county_name)
            for record in await govease.fetch_all(updated_since=updated_since):
                key = (record["county"], record["parcel_id"])
                if key in results:
                    results[key]["is_tax_delinquent"] = True
                    results[key].setdefault("raw_data", {})["govease"] = record.get("raw_data", {})
                else:
                    results[key] = record

    return {
        "records": list(results.values()),
        "primary_fetched": primary_fetched,
    }


async def run_delinquent_only(county: str = "all") -> list[dict]:
    """Fetch only tax-delinquent properties from counties that expose that field."""
    results: list[dict] = []
    for county_name in _resolve_counties(county):
        arcgis = ArcGISScraper(county=county_name)
        results.extend(await arcgis.fetch_delinquent_only())
    return results
