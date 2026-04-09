"""Shelby County, AL data scrapers."""
from .arcgis_scraper import ArcGISScraper
from .govease_scraper import GovEaseScraper

async def run_all_scrapers(limit: int = None) -> list[dict]:
    """Run all scrapers and merge results by parcel_id."""
    results = {}
    
    # Primary source: ArcGIS parcel data (106k parcels)
    arcgis = ArcGISScraper()
    for record in await arcgis.fetch_all(limit=limit):
        results[record["parcel_id"]] = record
    
    # Overlay: GovEase tax lien auction listings
    govease = GovEaseScraper()
    for record in await govease.fetch_all():
        pid = record["parcel_id"]
        if pid in results:
            results[pid]["is_tax_delinquent"] = True
            results[pid]["raw_data"]["govease"] = record.get("raw_data", {})
        else:
            results[pid] = record
    
    return list(results.values())


async def run_delinquent_only() -> list[dict]:
    """Fetch only tax-delinquent properties (faster)."""
    arcgis = ArcGISScraper()
    return await arcgis.fetch_delinquent_only()
