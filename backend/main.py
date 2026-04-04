"""
RSE — FastAPI Application Entry Point
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.export import router as export_router
from app.api.health import router as health_router
from app.api.leads import router as leads_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup / shutdown lifecycle."""
    print(f"[RSE] Starting up — env={settings.app_env}")
    yield
    print("[RSE] Shutting down.")


app = FastAPI(
    title="Real Estate Signal Engine",
    description="Transforms public property data into ranked seller/investor opportunities.",
    version="0.1.0",
    lifespan=lifespan,
)

# ── Routers ─────────────────────────────────────────────────────────────────
app.include_router(health_router)
app.include_router(leads_router)
app.include_router(export_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=(settings.app_env == "development"),
    )
