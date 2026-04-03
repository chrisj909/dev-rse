"""
RSE — Vercel Serverless Entry Point
api/index.py

Wraps the FastAPI app with Mangum so Vercel's Python runtime can invoke it
as a standard AWS Lambda / ASGI handler.

Vercel routes:
  - /api/*  → this file
  - /*      → frontend (Next.js)

Environment variables expected on Vercel:
  DATABASE_URL        — async-compatible Postgres URL, e.g.:
                        postgresql+asyncpg://user:pass@host/db
  APP_ENV             — "production" | "development" (default: "development")
  SCORING_VERSION     — e.g. "v1" (default: "v1")
  SCORE_THRESHOLD     — int, default 25
  WEBHOOK_URL         — optional, for Sprint 5 webhook delivery
  WEBHOOK_SECRET      — optional, for Sprint 5 webhook signing
"""
import os
import sys
from pathlib import Path

# ── Python path: make backend/ importable ─────────────────────────────────────
# In Vercel, the working directory is the project root (rse/).
# The FastAPI app lives in backend/, so we add it to sys.path.
_ROOT = Path(__file__).resolve().parent.parent   # rse/
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# ── Import the FastAPI application ────────────────────────────────────────────
from main import app  # noqa: E402  (after path manipulation)

# ── Wrap with Mangum for Vercel / Lambda compatibility ────────────────────────
# Mangum translates the Lambda event/context into an ASGI scope so FastAPI
# can handle requests without modification.
from mangum import Mangum  # noqa: E402

handler = Mangum(app, lifespan="off")
