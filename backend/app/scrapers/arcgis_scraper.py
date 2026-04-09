"""
Shelby County ArcGIS REST API scraper.
Endpoint: https://maps.shelbyal.com/gisserver/rest/services/LegacyServices/Cadastral_2022/MapServer/91
Fields confirmed live: PROPERTY_NUM, NAM1, NAM2, PROP_ADR, PROP_CITY, PROP_STATE, PROP_ZIP,
  MAIL_ADR, MAIL_CITY, MAIL_STATE, MAIL_ZIP, BD_EQL_VL, TAX_DUE_CD, TAX_SALE,
  HOMESTEAD_YR, INST_DATE1
"""
import asyncio
import httpx
from datetime import datetime

BASE_URL = (
    "https://maps.shelbyal.com/gisserver/rest/services/LegacyServices/"
    "Cadastral_2022/MapServer/91/query"
)
PAGE_SIZE = 1000


class ArcGISScraper:
    def __init__(self):
        self.params_base = {
            "f": "json",
            "outFields": ",".join([
                "PROPERTY_NUM", "NAM1", "NAM2", "PROP_ADR", "PROP_CITY",
                "PROP_STATE", "PROP_ZIP", "MAIL_ADR", "MAIL_CITY", "MAIL_STATE",
                "MAIL_ZIP", "BD_EQL_VL", "TAX_DUE_CD", "TAX_SALE",
                "HOMESTEAD_YR", "INST_DATE1",
            ]),
            "returnGeometry": "false",
            "resultRecordCount": PAGE_SIZE,
        }

    def _parse_record(self, attrs: dict) -> dict:
        prop_addr = (attrs.get("PROP_ADR") or "").strip()
        mail_addr = (attrs.get("MAIL_ADR") or "").strip()
        prop_city = (attrs.get("PROP_CITY") or "").strip()
        mail_city = (attrs.get("MAIL_CITY") or "").strip()

        is_absentee = bool(
            mail_addr and prop_addr and
            mail_addr.upper() != prop_addr.upper()
        )

        long_term_years = None
        inst_date = attrs.get("INST_DATE1")
        if inst_date:
            try:
                recorded = datetime.fromtimestamp(inst_date / 1000)
                years = (datetime.now() - recorded).days // 365
                if years >= 10:
                    long_term_years = years
            except Exception:
                pass

        owner_parts = [attrs.get("NAM1") or "", attrs.get("NAM2") or ""]
        owner_name = " ".join(p.strip() for p in owner_parts if p.strip())

        tax_due = (attrs.get("TAX_DUE_CD") or "").strip().upper()
        tax_sale = attrs.get("TAX_SALE")

        return {
            "parcel_id": str(attrs.get("PROPERTY_NUM") or "").strip(),
            "address": prop_addr,
            "city": prop_city,
            "owner_name": owner_name,
            "owner_mailing_address": f"{mail_addr}, {mail_city}".strip(", "),
            "assessed_value": float(attrs.get("BD_EQL_VL") or 0) or None,
            "is_tax_delinquent": tax_due in ("Y", "YES", "D") or bool(tax_sale),
            "is_absentee_owner": is_absentee,
            "long_term_owner_years": long_term_years,
            "is_probate": False,
            "is_pre_foreclosure": False,
            "raw_data": {
                "source": "arcgis",
                "tax_due_cd": attrs.get("TAX_DUE_CD"),
                "tax_sale": attrs.get("TAX_SALE"),
                "homestead_yr": attrs.get("HOMESTEAD_YR"),
            },
        }

    async def fetch_all(self, limit: int = None) -> list[dict]:
        records = []
        offset = 0
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                params = {**self.params_base, "where": "1=1", "resultOffset": offset}
                resp = await client.get(BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    raise RuntimeError(f"ArcGIS API error: {data['error']}")
                features = data.get("features", [])
                if not features:
                    break
                for f in features:
                    rec = self._parse_record(f.get("attributes", {}))
                    if rec["parcel_id"]:
                        records.append(rec)
                offset += PAGE_SIZE
                if limit and len(records) >= limit:
                    records = records[:limit]
                    break
                if not data.get("exceededTransferLimit", False) and len(features) < PAGE_SIZE:
                    break
                await asyncio.sleep(0.1)
        return records

    async def fetch_delinquent_only(self) -> list[dict]:
        records = []
        offset = 0
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                params = {**self.params_base, "where": "TAX_DUE_CD='Y' OR TAX_SALE IS NOT NULL", "resultOffset": offset}
                resp = await client.get(BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    raise RuntimeError(f"ArcGIS API error: {data['error']}")
                features = data.get("features", [])
                if not features:
                    break
                for f in features:
                    rec = self._parse_record(f.get("attributes", {}))
                    if rec["parcel_id"]:
                        rec["is_tax_delinquent"] = True
                        records.append(rec)
                offset += PAGE_SIZE
                if not data.get("exceededTransferLimit", False) and len(features) < PAGE_SIZE:
                    break
                await asyncio.sleep(0.1)
        return records
