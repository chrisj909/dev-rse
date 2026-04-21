"""County-aware ArcGIS parcel scrapers for Alabama county parcel data."""
import logging

import httpx
from datetime import datetime, timezone
from typing import Any

from .http_utils import polite_get_json, polite_page_pause

log = logging.getLogger("rse.scrapers.arcgis")

COUNTY_CONFIGS: dict[str, dict[str, Any]] = {
    "shelby": {
        "county": "shelby",
        "base_url": (
            "https://maps.shelbyal.com/gisserver/rest/services"
            "/LegacyServices/Cadastral_2022/MapServer/91/query"
        ),
        "fields": [
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
        ],
        "page_size": 1000,
        "order_by_field": "OBJECTID",
        "default_where": "1=1",
        "delinquent_where": "TAX_DUE_CD='Y'",
        "updated_field": "Transcreate_Save",
    },
    "jefferson": {
        "county": "jefferson",
        "base_url": "https://jccgis.jccal.org/server/rest/services/Basemap/Parcels/MapServer/0/query",
        "fields": [
            "PARCELID",
            "OWNERNAME",
            "Name2",
            "Bldg_Number",
            "Street_Name",
            "Street_Type",
            "Street_Dir",
            "APARTMENT",
            "PROP_MAIL",
            "CITYMAIL",
            "STATE_Mail",
            "ZIP_MAIL",
            "Property_City",
            "Property_State",
            "ZIP",
            "AssdValue",
        ],
        "page_size": 2000,
        "order_by_field": "OBJECTID",
        "default_where": (
            "PARCELID IS NOT NULL AND PARCELID <> '' "
            "AND (Street_Name IS NOT NULL OR OWNERNAME IS NOT NULL OR PROP_MAIL IS NOT NULL)"
        ),
        "delinquent_where": None,
    },
}


def _centroid_from_geometry(geom: dict | None) -> tuple[float | None, float | None]:
    """Return (lat, lng) in WGS84 from an ArcGIS geometry object.

    Handles point features (x/y) and polygon features (rings).
    Expects coordinates already projected to WGS84 via outSR=4326.
    """
    if not geom:
        return None, None
    if "x" in geom and "y" in geom:
        x, y = geom["x"], geom["y"]
        if x is None or y is None:
            return None, None
        return float(y), float(x)
    if "rings" in geom:
        ring = geom["rings"][0] if geom["rings"] else []
        if not ring:
            return None, None
        cx = sum(pt[0] for pt in ring) / len(ring)
        cy = sum(pt[1] for pt in ring) / len(ring)
        return float(cy), float(cx)
    return None, None


def _parse_inst_date(val: Any) -> datetime | None:
    """INST_DATE1 is stored as YYYYMMDD integer, e.g. 20091120."""
    if not val:
        return None
    try:
        s = str(int(val))
        return datetime(int(s[:4]), int(s[4:6]), int(s[6:8]), tzinfo=timezone.utc)
    except Exception:
        return None


def _normalize_county(county: str | None) -> str:
    normalized = (county or "shelby").strip().lower()
    if normalized not in COUNTY_CONFIGS:
        raise ValueError(f"Unsupported county: {county}")
    return normalized


def _normalize_updated_since(updated_since: datetime | None) -> datetime | None:
    if updated_since is None:
        return None
    if updated_since.tzinfo is None:
        return updated_since.replace(tzinfo=timezone.utc)
    return updated_since.astimezone(timezone.utc)


def _build_where_clause(config: dict[str, Any], updated_since: datetime | None = None) -> str:
    base_where = str(config["default_where"])
    normalized_updated_since = _normalize_updated_since(updated_since)
    updated_field = config.get("updated_field")

    if normalized_updated_since is None:
        return base_where

    if not updated_field:
        log.warning(
            "Incremental retrieval requested for county=%s, but no supported updated field is configured; falling back to full fetch.",
            config.get("county", "unknown"),
        )
        return base_where

    timestamp_literal = normalized_updated_since.strftime("%Y-%m-%d %H:%M:%S")
    return f"({base_where}) AND {updated_field} >= DATE '{timestamp_literal}'"


def _record_to_dict_shelby(attrs: dict, geom: dict | None = None) -> dict:
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

    lat, lng = _centroid_from_geometry(geom)

    return {
        "county": "shelby",
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
        "lat": lat,
        "lng": lng,
        "raw": attrs,
    }


def _compose_jefferson_address(attrs: dict) -> str | None:
    parts = [
        attrs.get("Bldg_Number"),
        attrs.get("Street_Dir"),
        attrs.get("Street_Name"),
        attrs.get("Street_Type"),
        attrs.get("APARTMENT"),
    ]
    text_parts = [str(part).strip() for part in parts if part not in (None, "") and str(part).strip()]
    return " ".join(text_parts) or None


def _record_to_dict_jefferson(attrs: dict, geom: dict | None = None) -> dict:
    parcel_id = attrs.get("PARCELID") or ""
    if not parcel_id:
        return {}

    owner_parts = [attrs.get("OWNERNAME") or "", attrs.get("Name2") or ""]
    owner_name = " ".join(part.strip() for part in owner_parts if str(part).strip()) or None

    prop_adr = _compose_jefferson_address(attrs)
    city = (attrs.get("Property_City") or attrs.get("CITY") or "").strip() or None
    state = (attrs.get("Property_State") or "AL").strip() or "AL"

    prop_zip_raw = attrs.get("ZIP")
    prop_zip = str(prop_zip_raw).strip() if prop_zip_raw not in (None, "") else None
    if prop_zip and prop_zip.isdigit():
        prop_zip = prop_zip.zfill(5)

    mail_street = (attrs.get("PROP_MAIL") or "").strip()
    mail_city = (attrs.get("CITYMAIL") or "").strip()
    mail_state = (attrs.get("STATE_Mail") or state or "AL").strip() or "AL"
    mail_zip = (attrs.get("ZIP_MAIL") or "").strip() or None
    if mail_zip and mail_zip.isdigit():
        mail_zip = mail_zip.zfill(5)
    mailing_address = " ".join(part for part in [mail_street, mail_city, mail_state, mail_zip] if part)

    assessed_raw = attrs.get("AssdValue")
    try:
        assessed_value = float(assessed_raw) if assessed_raw is not None else None
    except (TypeError, ValueError):
        assessed_value = None

    is_absentee = bool(
        prop_adr
        and mail_street
        and prop_adr.upper() != mail_street.upper()
    )

    lat, lng = _centroid_from_geometry(geom)

    return {
        "county": "jefferson",
        "parcel_id": str(parcel_id).strip(),
        "address": prop_adr,
        "raw_address": prop_adr,
        "city": city,
        "state": state,
        "zip": prop_zip,
        "owner_name": owner_name,
        "mailing_address": mailing_address or None,
        "raw_mailing_address": mail_street or None,
        "last_sale_date": None,
        "assessed_value": assessed_value,
        "is_tax_delinquent": False,
        "is_absentee_owner": is_absentee,
        "long_term_owner_years": None,
        "lat": lat,
        "lng": lng,
        "raw": attrs,
    }


def _record_to_dict(attrs: dict, county: str, geom: dict | None = None) -> dict:
    normalized = _normalize_county(county)
    if normalized == "jefferson":
        return _record_to_dict_jefferson(attrs, geom)
    return _record_to_dict_shelby(attrs, geom)


async def fetch_all(
    limit: int | None = None,
    county: str = "shelby",
    updated_since: datetime | None = None,
    start_offset: int = 0,
) -> list[dict]:
    """Paginate through all parcels using OBJECTID cursor pagination.

    start_offset is treated as an OBJECTID cursor — fetch records with
    OBJECTID > start_offset.  0 means start from the first record.
    Each returned dict includes a ``_objectid`` key for cursor tracking.
    """
    results: list[dict] = []
    cursor = start_offset
    config = COUNTY_CONFIGS[_normalize_county(county)]
    page_size = int(config["page_size"])
    base_where = _build_where_clause(config, updated_since)
    order_field = config["order_by_field"]
    out_fields = [*config["fields"], order_field]

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            remaining = None if limit is None else max(limit - len(results), 0)
            if remaining == 0:
                break

            # OBJECTID cursor avoids ArcGIS resultOffset limits (~33 K on Jefferson).
            if cursor > 0:
                where = f"({base_where}) AND {order_field} > {cursor}"
            else:
                where = base_where

            params = {
                "where": where,
                "outFields": ",".join(out_fields),
                "orderByFields": f"{order_field} ASC",
                "resultRecordCount": min(page_size, remaining) if remaining is not None else page_size,
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "json",
            }
            data = await polite_get_json(client, config["base_url"], params=params)

            features = data.get("features", [])
            if not features:
                break

            for feat in features:
                attrs = feat.get("attributes", {})
                objectid = attrs.get(order_field)
                row = _record_to_dict(attrs, config["county"], feat.get("geometry"))
                if row:
                    if objectid is not None:
                        row["_objectid"] = int(objectid)
                        cursor = max(cursor, int(objectid))
                    results.append(row)
                    if limit and len(results) >= limit:
                        return results

            if len(features) < page_size:
                break
            await polite_page_pause()

    return results


async def fetch_delinquent_only(county: str = "shelby") -> list[dict]:
    """Fetch only tax-delinquent parcels where the source supports it."""
    results: list[dict] = []
    offset = 0
    config = COUNTY_CONFIGS[_normalize_county(county)]
    if not config.get("delinquent_where"):
        return results
    page_size = int(config["page_size"])

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            params = {
                "where": config["delinquent_where"],
                "outFields": ",".join(config["fields"]),
                "orderByFields": f"{config['order_by_field']} ASC",
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "json",
            }
            data = await polite_get_json(client, config["base_url"], params=params)

            features = data.get("features", [])
            if not features:
                break

            for feat in features:
                row = _record_to_dict(feat.get("attributes", {}), config["county"], feat.get("geometry"))
                if row:
                    results.append(row)

            offset += page_size
            if not data.get("exceededTransferLimit", False) and len(features) < page_size:
                break
            await polite_page_pause()

    return results


class ArcGISScraper:
    """Class wrapper for backwards-compatible import by app.scrapers.__init__."""

    def __init__(self, county: str = "shelby") -> None:
        self.county = _normalize_county(county)

    async def fetch_all(
        self,
        limit: int | None = None,
        updated_since: datetime | None = None,
        start_offset: int = 0,
    ) -> list[dict]:
        return await fetch_all(
            limit=limit,
            county=self.county,
            updated_since=updated_since,
            start_offset=start_offset,
        )

    async def fetch_delinquent_only(self) -> list[dict]:
        return await fetch_delinquent_only(county=self.county)
