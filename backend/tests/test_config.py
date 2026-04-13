from urllib.parse import parse_qs, urlsplit

import pytest

from app.core.config import Settings


def test_local_database_url_stays_async_without_pgbouncer_args():
    settings = Settings(
        database_url="postgresql://user:pass@db:5432/rse_db",
        database_sync_url="postgresql://user:pass@db:5432/rse_db",
    )

    assert settings.get_async_database_url() == "postgresql+asyncpg://user:pass@db:5432/rse_db"
    assert settings.get_async_connect_args() == {}


def test_pgbouncer_database_url_disables_prepared_statement_cache():
    settings = Settings(
        database_url=(
            "postgresql://user:pass@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
            "?pgbouncer=true&sslmode=require"
        ),
        database_sync_url="postgresql://user:pass@db:5432/rse_db",
    )

    parsed = urlsplit(settings.get_async_database_url())
    query = parse_qs(parsed.query)

    assert parsed.scheme == "postgresql+asyncpg"
    assert query["pgbouncer"] == ["true"]
    assert query["prepared_statement_cache_size"] == ["0"]
    assert query["sslmode"] == ["require"]


def test_pgbouncer_connect_args_disable_statement_cache_and_use_unique_names():
    settings = Settings(
        database_url=(
            "postgresql+asyncpg://user:pass@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
            "?pgbouncer=true"
        ),
        database_sync_url="postgresql://user:pass@db:5432/rse_db",
    )

    connect_args = settings.get_async_connect_args()

    assert connect_args["statement_cache_size"] == 0

    first_name = connect_args["prepared_statement_name_func"]()
    second_name = connect_args["prepared_statement_name_func"]()

    assert first_name.startswith("__asyncpg_")
    assert second_name.startswith("__asyncpg_")
    assert first_name != second_name


def test_sync_database_url_derived_from_async_url_when_sync_url_not_set():
    settings = Settings(
        database_url="postgresql+asyncpg://user:pass@db.example.com:5432/postgres",
        database_sync_url="",
    )

    assert settings.get_sync_database_url() == "postgresql://user:pass@db.example.com:5432/postgres"


def test_production_local_database_url_is_rejected():
    settings = Settings(
        app_env="production",
        database_url="postgresql://user:pass@db:5432/rse_db",
        database_sync_url="",
    )

    with pytest.raises(ValueError, match="local database URL"):
        settings.get_async_database_url()