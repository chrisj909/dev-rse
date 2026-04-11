"""Shelby County ArcGIS parcel scraper."""
from datetime import datetime, timezone
from typing import Any

import httpx

BASE_URL = (
    "https://maps.shelbyal.com/gisserver/rest/services"
    "/LegacyServices/Cadastral_2022/MapServer/91/query"
)

FIELDS = [
    "PROPERTY_NUM",
    "NAM1",
    "NAM2",
    "PROP_ADR",
    "ADR1",
    "ADR2",
    "CITY",
    "STATE",
    "ZIP",
    "BD_EQL_VL",
    "TAX_DUE_CD",
    "TAX_SALE",
    "HOMESTEAD_YR",
    "INST_DATE1",
]


def _parse_inst_date(val: Any) -> datetime | None:
    """INST_DATE1 is stored as YYYYMMDD integer, e.g. 20091120."""
    if not val:
        return None
    try:
        s = str(int(val))
        return datetime(int(s[:4]), int(s[4:6]), int(s[6:8]), tzinfo=timezone.utc)
    except Exception:
        return None


def _record_to_dict(attrs: dict) -> dict:
    parcel_id = attrs.get("PROPERTY_NUM") or ""
    if not parcel_id:
        return {}

    owner_parts = [attrs.get("NAM1") or "", attrs.get("NAM2") or ""]
    owner_name = " ".join(p.strip() for p in owner_parts if p.strip()) or None

    prop_adr = (attrs.get("PROP_ADR") or "").strip()
    mail_adr = (attrs.get("ADR1") or "").strip()
    city = (attrs.get("CITY") or "").strip()
    state = (attrs.get("STATE") or "AL").strip() or "AL"
    zip_code_raw = attrs.get("ZIP")
    zip_code = str(zip_code_raw).strip() if zip_code_raw not in (None, "") else None
    if zip_code and zip_code.isdigit():
        zip_code = zip_code.zfill(5)

    mailing_parts = [mail_adr, city, state, zip_code]
    mailing_address = " ".join(part for part in mailing_parts if part)

    is_absentee = bool(
        prop_adr
        and mail_adr
        and prop_adr.upper() != mail_adr.upper()
    )

    inst_date = _parse_inst_date(attrs.get("INST_DATE1"))
    long_term_years: int | None = None
    if inst_date:
        years = (datetime.now(timezone.utc) - inst_date).days / 365.25
        if years >= 10:
            long_term_years = int(years)

    tax_due = str(attrs.get("TAX_DUE_CD") or "").strip().upper()
    is_delinquent = tax_due == "Y"

    assessed_raw = attrs.get("BD_EQL_VL")
    try:
        assessed_value = float(assessed_raw) if assessed_raw is not None else None
    except (TypeError, ValueError):
        assessed_value = None

    return {
        "parcel_id": str(parcel_id).strip(),
        "address": prop_adr or None,
        "raw_address": prop_adr or None,
        "city": city or None,
        "state": state,
        "zip": zip_code,
        "owner_name": owner_name,
        "mailing_address": mailing_address or None,
        "raw_mailing_address": mail_adr or None,
        "last_sale_date": inst_date.date() if inst_date else None,
        "assessed_value": assessed_value,
        "is_tax_delinquent": is_delinquent,
        "is_absentee_owner": is_absentee,
        "long_term_owner_years": long_term_years,
        "raw": attrs,
    }


async def fetch_all(limit: int | None = None) -> list[dict]:
    """Paginate through all parcels. Honours optional limit."""
    results: list[dict] = []
    offset = 0
    page_size = 1000

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            params = {
                "where": "1=1",
                "outFields": ",".join(FIELDS),
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "f": "json",
            }
            resp = await client.get(BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                raise RuntimeError(f"ArcGIS API error: {data['error']}")

            features = data.get("features", [])
            if not features:
                break

            for feat in features:
                row = _record_to_dict(feat.get("attributes", {}))
                if row:
                    results.append(row)
                    if limit and len(results) >= limit:
                        return results

            offset += page_size
            if not data.get("exceededTransferLimit", False) and len(features) < page_size:
                break

    return results


async def fetch_delinquent_only() -> list[dict]:
    """Fetch only tax-delinquent parcels."""
    results: list[dict] = []
    offset = 0
    page_size = 1000

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            params = {
                "where": "TAX_DUE_CD='Y'",
                "outFields": ",".join(FIELDS),
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "f": "json",
            }
            resp = await client.get(BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                raise RuntimeError(f"ArcGIS API error: {data['error']}")

            features = data.get("features", [])
            if not features:
                break

            for feat in features:
                row = _record_to_dict(feat.get("attributes", {}))
                if row:
                    results.append(row)

            offset += page_size
            if not data.get("exceededTransferLimit", False) and len(features) < page_size:
                break

    return results


class ArcGISScraper:
    """Class wrapper for backwards-compatible import by app.scrapers.__init__."""

    async def fetch_all(self, limit: int | None = None) -> list[dict]:
        return await fetch_all(limit=limit)

    async def fetch_delinquent_only(self) -> list[dict]:
        return await fetch_delinquent_only()
