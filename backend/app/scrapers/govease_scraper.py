"""GovEase tax lien auction scraper for county overlays that are currently supported."""
from datetime import datetime

import httpx

from .http_utils import polite_get_json

API_URL = "https://api.govease.com/api/properties"


class GovEaseScraper:
    def __init__(self, county: str = "shelby") -> None:
        self.county = (county or "shelby").strip().lower()

    async def fetch_all(self, updated_since: datetime | None = None) -> list[dict]:
        del updated_since
        if self.county != "shelby":
            return []
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                data = await polite_get_json(
                    client,
                    API_URL,
                    params={"state": "AL", "county": self.county, "page": 1, "per_page": 500},
                    headers={"Accept": "application/json"},
                )
                if isinstance(data, dict):
                    props = data.get("properties") or []
                elif isinstance(data, list):
                    props = data
                else:
                    props = []
                return [self._parse(p) for p in props if p.get("parcel_number")]
        except Exception:
            pass
        return []

    def _parse(self, p: dict) -> dict:
        return {
            "county": self.county,
            "parcel_id": str(p.get("parcel_number", "")).strip(),
            "address": p.get("address", ""),
            "city": p.get("city", ""),
            "owner_name": p.get("owner_name", ""),
            "owner_mailing_address": "",
            "assessed_value": p.get("assessed_value"),
            "is_tax_delinquent": True,
            "is_absentee_owner": False,
            "is_probate": False,
            "is_pre_foreclosure": False,
            "long_term_owner_years": None,
            "raw_data": {"source": "govease", "auction_data": p},
        }
