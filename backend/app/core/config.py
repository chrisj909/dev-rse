"""
RSE Core Configuration
Loads settings from environment / .env file via pydantic-settings.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Database
    # DATABASE_URL is the primary setting — set this env var on Vercel (Neon,
    # Supabase, etc.) or in .env for local Docker Compose.
    # Must use an asyncpg-compatible scheme: postgresql+asyncpg://...
    # For sync access (Alembic migrations), a sync URL is derived below.
    database_url: str = "postgresql+asyncpg://rse_user:rse_password@db:5432/rse_db"
    database_sync_url: str = "postgresql://rse_user:rse_password@db:5432/rse_db"

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
        return url

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
    score_threshold: int = 25

    # Webhooks (Sprint 6)
    webhook_url: str = ""
    webhook_secret: str = ""
    webhook_score_threshold: int = 25  # fire webhook when score >= this value


settings = Settings()
