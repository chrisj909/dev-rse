"""
RSE Core Configuration
Loads settings from environment / .env file via pydantic-settings.
"""
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from pydantic_settings import BaseSettings, SettingsConfigDict


_ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ROOT_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Database
    # DATABASE_URL is the primary setting â set this env var on Vercel (Neon,
    # Supabase, etc.) or in .env for local Docker Compose.
    # Must use an asyncpg-compatible scheme: postgresql+asyncpg://...
    # For sync access (Alembic migrations), a sync URL is derived below.
    database_url: str = "postgresql+asyncpg://rse_user:rse_password@db:5432/rse_db"
    database_sync_url: str = "postgresql://rse_user:rse_password@db:5432/rse_db"

    def uses_pgbouncer(self) -> bool:
        """Detect pooled Postgres URLs that require PgBouncer-safe asyncpg settings."""
        parsed = urlsplit(self.database_url)
        hostname = (parsed.hostname or "").lower()
        query = {key.lower(): value.lower() for key, value in parse_qsl(parsed.query, keep_blank_values=True)}

        return (
            query.get("pgbouncer") == "true"
            or query.get("pool_mode") in {"transaction", "statement"}
            or "pooler.supabase.com" in hostname
            or hostname.startswith("aws-0-") and "pooler" in hostname
        )

    def get_async_database_url(self) -> str:
        """
        Return an asyncpg-compatible database URL.
        Handles Neon/Supabase connection strings that use the bare
        'postgresql://' scheme by upgrading them to 'postgresql+asyncpg://'.
        """
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

        if self.uses_pgbouncer():
            parsed = urlsplit(url)
            query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
            query = dict(query_pairs)
            query.setdefault("prepared_statement_cache_size", "0")
            url = urlunsplit(parsed._replace(query=urlencode(query)))
        return url

    def get_async_connect_args(self) -> dict[str, Any]:
        """
        Return asyncpg connect args.

        Supabase pooled connections sit behind PgBouncer transaction pooling,
        which is incompatible with asyncpg's default prepared statement usage.
        Disable statement caching and force unique prepared-statement names.
        """
        if not self.uses_pgbouncer():
            return {}

        return {
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
        }

    def get_sync_database_url(self) -> str:
        """
        Return a psycopg2-compatible (synchronous) database URL for Alembic.
        Strips any asyncpg driver marker.
        """
        url = self.database_sync_url or self.database_url
        url = url.replace("postgresql+asyncpg://", "postgresql://")
        url = url.replace("postgres://", "postgresql://")
        return url

    # Scoring
    scoring_version: str = "v1"
    score_threshold: float = 25

    # Webhooks (Sprint 6)
    webhook_url: str = ""
    webhook_secret: str = ""
    webhook_score_threshold: float = 25  # fire webhook when score >= this value


    # Ingest security
    cron_secret: str = ""

    # Frontend integration
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    def get_cors_allowed_origins(self) -> list[str]:
        """Return configured CORS origins as a normalized list."""
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

settings = Settings()
