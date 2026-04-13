"""Alembic migration environment.
Uses DATABASE_SYNC_URL from .env for synchronous migrations.
Auto-generates migrations from SQLAlchemy models.
"""
import os
import sys
from logging.config import fileConfig
from urllib.parse import urlsplit

from alembic import context
from sqlalchemy import engine_from_config, pool
from dotenv import load_dotenv

# Ensure the backend package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Load .env so DATABASE_SYNC_URL is available
load_dotenv()

# Import Base + all models so Alembic sees the metadata
from app.db.session import Base  # noqa: E402
import app.models  # noqa: E402, F401  — registers all models on Base.metadata

# Alembic config object
config = context.config

def _derive_sync_url() -> str:
    sync_url = os.getenv("DATABASE_SYNC_URL", "").strip()
    if sync_url:
        return sync_url

    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        return (
            database_url
            .replace("postgresql+asyncpg://", "postgresql://")
            .replace("postgres://", "postgresql://")
        )

    return "postgresql://rse_user:rse_password@db:5432/rse_db"


def _is_local_database_url(url: str) -> bool:
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower()
    return hostname in {"", "localhost", "127.0.0.1", "db"}


# Override sqlalchemy.url with the sync URL from environment
sync_url = _derive_sync_url()
runtime_env = (os.getenv("APP_ENV") or os.getenv("VERCEL_ENV") or "development").strip().lower()
if runtime_env == "production" and _is_local_database_url(sync_url):
    raise RuntimeError(
        "Alembic resolved a local DATABASE_SYNC_URL while APP_ENV is production. "
        "Run migrations from a shell with Supabase/Vercel database env vars set."
    )
# configparser treats % as interpolation — escape them before setting
config.set_main_option("sqlalchemy.url", sync_url.replace("%", "%%"))

# Configure Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (live DB connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
