"""
RSE Test Configuration
pytest fixtures shared across the test suite.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from main import app
from app.db.session import get_db, get_session


# ── Session / client fixtures ─────────────────────────────────────────────────

@pytest.fixture
def mock_session() -> AsyncMock:
    """Return a fresh mock async database session for each test."""
    return AsyncMock()


@pytest.fixture
def test_client(mock_session: AsyncMock):
    """
    Return a FastAPI TestClient with the DB dependency overridden.

    The mock_session is injected instead of a real async session so no
    database connection is required during tests.
    """
    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


# ── ORM mock factories ────────────────────────────────────────────────────────

def make_mock_property(
    *,
    prop_id: uuid.UUID | None = None,
    county: str = "shelby",
    parcel_id: str = "SC-TEST-0001",
    address: str | None = "123 MAIN ST",
    city: str | None = "HOOVER",
    state: str = "AL",
    zip_code: str | None = "35244",
    owner_name: str | None = "JOHN DOE",
    mailing_address: str | None = "456 OTHER ST",
    raw_mailing_address: str | None = "456 Other St",
    raw_address: str | None = "123 Main Street",
    last_sale_date: date | None = None,
    assessed_value: float | None = 150000.00,
) -> MagicMock:
    """Build a mock Property ORM object with sensible defaults."""
    prop = MagicMock()
    prop.id = prop_id or uuid.uuid4()
    prop.county = county
    prop.parcel_id = parcel_id
    prop.address = address
    prop.raw_address = raw_address
    prop.city = city
    prop.state = state
    prop.zip = zip_code
    prop.owner_name = owner_name
    prop.mailing_address = mailing_address
    prop.raw_mailing_address = raw_mailing_address
    prop.last_sale_date = last_sale_date
    prop.assessed_value = assessed_value
    prop.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    prop.updated_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
    return prop


def make_mock_signal(
    *,
    property_id: uuid.UUID | None = None,
    absentee_owner: bool = False,
    long_term_owner: bool = False,
    tax_delinquent: bool = False,
    pre_foreclosure: bool = False,
    probate: bool = False,
    eviction: bool = False,
    code_violation: bool = False,
) -> MagicMock:
    """Build a mock Signal ORM object."""
    sig = MagicMock()
    sig.id = uuid.uuid4()
    sig.property_id = property_id or uuid.uuid4()
    sig.absentee_owner = absentee_owner
    sig.long_term_owner = long_term_owner
    sig.tax_delinquent = tax_delinquent
    sig.pre_foreclosure = pre_foreclosure
    sig.probate = probate
    sig.eviction = eviction
    sig.code_violation = code_violation
    return sig


def make_mock_score(
    *,
    property_id: uuid.UUID | None = None,
    score: int = 25,
    rank: str = "A",
    reason: list[str] | None = None,
    scoring_version: str = "v2",
    last_updated: datetime | None = None,
) -> MagicMock:
    """Build a mock Score ORM object."""
    sc = MagicMock()
    sc.id = uuid.uuid4()
    sc.property_id = property_id or uuid.uuid4()
    sc.score = score
    sc.rank = rank
    sc.reason = reason if reason is not None else ["absentee_owner", "long_term_owner"]
    sc.scoring_version = scoring_version
    sc.last_updated = last_updated or datetime(2026, 3, 28, tzinfo=timezone.utc)
    return sc
