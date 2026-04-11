"""
RSE â FastAPI Application Entry Point
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.cron import router as cron_router
from app.api.export import router as export_router
from app.api.health import router as health_router
from app.api.leads import router as leads_router
from app.api import ingest
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup / shutdown lifecycle."""
    print(f"[RSE] Starting up â env={settings.app_env}")
    yield
    print("[RSE] Shutting down.")


app = FastAPI(
    title="Real Estate Signal Engine",
    description="Transforms public property data into ranked seller/investor opportunities.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_allowed_origins(),
    allow_origin_regex=r"https://.*\.(app\.github\.dev|githubpreview\.dev)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ââ Routers âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
app.include_router(health_router, prefix="/api")
app.include_router(export_router, prefix="/api")
app.include_router(leads_router, prefix="/api")
app.include_router(ingest.router, prefix="/api")
app.include_router(cron_router, prefix="/api/cron")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=(settings.app_env == "development"),
    )
