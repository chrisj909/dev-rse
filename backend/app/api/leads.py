"""
RSE Lead Endpoints — Sprint 4, Task 11 (stub)
app/api/leads.py

GET /api/leads/top — returns top-scored properties, sorted by score DESC.

Sprint 4 stub: the endpoint is live and returns a well-typed empty response.
Full DB join + filtering + pagination will be implemented in Sprint 4
Tasks 11–12 once the scoring engine has populated the scores table.

Response shape (matches the Sprint 5 clean API contract):
  {
    "leads": [
      {
        "property_id": str,
        "parcel_id":   str,
        "address":     str,
        "city":        str,
        "owner_name":  str | null,
        "score":       int,
        "rank":        str,
        "signals":     { signal_name: bool, ... },
        "tags":        [str, ...],
        "last_updated": str (ISO 8601)
      }
    ],
    "total": int
  }
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["leads"])


@router.get("/leads/top")
async def get_top_leads():
    """
    Top-ranked properties by signal score.

    Returns the highest-scored properties (default limit 50), sorted by
    score descending. Responds with an empty leads array until the scoring
    engine has been run and score rows exist in the database.

    Query parameters (Sprint 4 Task 12 — to be implemented):
      limit         int  — max results (default 50)
      offset        int  — pagination offset (default 0)
      min_score     int  — minimum score threshold
      absentee_owner bool — filter to absentee-owned properties only
      city          str  — filter by city name

    Returns:
        {"leads": [...], "total": int}
    """
    # Stub — Sprint 4 Task 11 will add the DB join:
    # SELECT p.*, s.*, sc.*
    # FROM properties p
    # JOIN signals s  ON s.property_id = p.id
    # JOIN scores  sc ON sc.property_id = p.id
    # ORDER BY sc.score DESC
    # LIMIT :limit OFFSET :offset
    return {"leads": [], "total": 0}
