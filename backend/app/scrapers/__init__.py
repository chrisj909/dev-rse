"""County-aware parcel and overlay scrapers."""
from datetime import datetime

from .arcgis_scraper import ArcGISScraper
from .govease_scraper import GovEaseScraper

SUPPORTED_COUNTIES = ("shelby", "jefferson")


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
    """Run county scrapers and merge results by (county, parcel_id)."""
    results: dict[tuple[str, str], dict] = {}
    counties = _resolve_counties(county)

    if start_offset and len(counties) != 1:
        raise ValueError("start_offset is only supported for single-county ingest runs")

    for county_name in counties:
        arcgis = ArcGISScraper(county=county_name)
        for record in await arcgis.fetch_all(
            limit=limit,
            updated_since=updated_since,
            start_offset=start_offset,
        ):
            results[(record["county"], record["parcel_id"])] = record

        govease = GovEaseScraper(county=county_name)
        for record in await govease.fetch_all(updated_since=updated_since):
            key = (record["county"], record["parcel_id"])
            if key in results:
                results[key]["is_tax_delinquent"] = True
                results[key].setdefault("raw_data", {})["govease"] = record.get("raw_data", {})
            else:
                results[key] = record

    return list(results.values())


async def run_delinquent_only(county: str = "all") -> list[dict]:
    """Fetch only tax-delinquent properties from counties that expose that field."""
    results: list[dict] = []
    for county_name in _resolve_counties(county):
        arcgis = ArcGISScraper(county=county_name)
        results.extend(await arcgis.fetch_delinquent_only())
    return results
