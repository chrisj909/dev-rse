"""
RSE Address Normalization Utility
app/services/address_normalizer.py

Produces a canonical address string from raw input for consistent matching.
Design rules:
  - Always store the raw original alongside the normalized output.
  - Normalization is deterministic: same input always produces same output.
  - parcel_id remains the primary dedupe key; normalized addresses aid matching only.
"""
import re
from typing import Optional


# ── Suffix / abbreviation tables ────────────────────────────────────────────

STREET_SUFFIXES: dict[str, str] = {
    "STREET": "ST",
    "ROAD": "RD",
    "AVENUE": "AVE",
    "BOULEVARD": "BLVD",
    "DRIVE": "DR",
    "LANE": "LN",
    "COURT": "CT",
    "PLACE": "PL",
    "CIRCLE": "CIR",
    "TERRACE": "TER",
    "WAY": "WAY",
    "HIGHWAY": "HWY",
    "TRAIL": "TRL",
    "PARKWAY": "PKWY",
    "LOOP": "LOOP",
    "PASS": "PASS",
    "PATH": "PATH",
}

DIRECTIONALS: dict[str, str] = {
    "NORTH": "N",
    "SOUTH": "S",
    "EAST": "E",
    "WEST": "W",
    "NORTHEAST": "NE",
    "NORTHWEST": "NW",
    "SOUTHEAST": "SE",
    "SOUTHWEST": "SW",
}

# Unit/apartment/suite designators → canonical prefix
UNIT_VARIANTS: dict[str, str] = {
    "APARTMENT": "APT",
    "APT": "APT",
    "SUITE": "STE",
    "STE": "STE",
    "UNIT": "UNIT",
    "NUMBER": "#",
    "NO": "#",
    "#": "#",
    "ROOM": "RM",
    "RM": "RM",
    "FLOOR": "FL",
    "FL": "FL",
}

# Punctuation to strip (keep hyphens in house numbers, e.g. "123-A")
_PUNCT_RE = re.compile(r"[.,;:\"'`]")

# Collapse multiple whitespace
_WS_RE = re.compile(r"\s{2,}")


def normalize_address(raw: Optional[str]) -> Optional[str]:
    """
    Normalize a raw address string to a canonical form.

    Steps:
      1. Guard — return None for empty/None input.
      2. Uppercase.
      3. Strip punctuation (commas, periods, etc.).
      4. Normalize unit designators.
      5. Normalize street suffixes.
      6. Normalize directionals.
      7. Collapse whitespace and strip.

    Args:
        raw: The raw address string as ingested from a CSV or external source.

    Returns:
        Canonical address string, or None if input is blank.

    Examples:
        >>> normalize_address("123 North Main Street, Apt 4")
        '123 N MAIN ST APT 4'
        >>> normalize_address("456 oak avenue suite 200")
        '456 OAK AVE STE 200'
    """
    if not raw or not raw.strip():
        return None

    text = raw.strip().upper()

    # Step 1 — strip punctuation
    text = _PUNCT_RE.sub(" ", text)

    # Step 2 — normalize unit designators
    # Match "UNIT_WORD NUMBER" or "UNIT_WORD LETTER" patterns
    for variant, canonical in UNIT_VARIANTS.items():
        # Only replace if followed by a space and identifier (not mid-word)
        text = re.sub(
            rf"\b{re.escape(variant)}\b\s*",
            canonical + " ",
            text,
        )

    # Step 3 — normalize street suffixes
    # Only replace whole words at word boundaries
    for full, abbr in STREET_SUFFIXES.items():
        text = re.sub(rf"\b{re.escape(full)}\b", abbr, text)

    # Step 4 — normalize directionals
    # Directionals appear at the start of an address (e.g. "N Main") or
    # after a street number as a prefix (e.g. "123 NORTH MAIN").
    # We normalize all standalone occurrences.
    for full, abbr in DIRECTIONALS.items():
        text = re.sub(rf"\b{re.escape(full)}\b", abbr, text)

    # Step 5 — collapse whitespace
    text = _WS_RE.sub(" ", text).strip()

    return text


def normalize_address_pair(
    raw_property: Optional[str],
    raw_mailing: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """
    Normalize both the property address and the mailing address in one call.

    Returns:
        (normalized_property_address, normalized_mailing_address)
    """
    return normalize_address(raw_property), normalize_address(raw_mailing)


def addresses_match(addr_a: Optional[str], addr_b: Optional[str]) -> bool:
    """
    Compare two already-normalized addresses for equality.
    Returns False if either address is None (insufficient data).

    Used by absentee_owner signal: if property_address != mailing_address → absentee.
    """
    if addr_a is None or addr_b is None:
        return False
    return addr_a.strip() == addr_b.strip()
