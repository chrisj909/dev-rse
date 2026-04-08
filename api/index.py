"""
RSE - Vercel Serverless Entry Point  api/index.py

Routes registered with prefix="/api" in backend/main.py,
so Vercel passes /api/health directly to FastAPI - no stripping needed.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
      sys.path.insert(0, str(_BACKEND))

from main import app  # noqa: E402
from mangum import Mangum  # noqa: E402

handler = Mangum(app, lifespan="off")
