"""RSE Database Session Management - NullPool for serverless.
Provides async SQLAlchemy engine, session factory, and ORM Base.
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings


# Async engine - NullPool prevents connection reuse across serverless invocations
engine = create_async_engine(
    settings.get_async_database_url(),
    echo=(settings.app_env == "development"),
    poolclass=NullPool,
    connect_args=settings.get_async_connect_args(),
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency - yields a database session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Alias used by ingest router
async def get_session() -> AsyncSession:
    """Alias for get_db() - used by ingest endpoints."""
    async for session in get_db():
        yield session
