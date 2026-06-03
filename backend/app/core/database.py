from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# pool_pre_ping sends a cheap "SELECT 1" before each checkout to detect stale
# connections — important in Docker where the DB can restart.
engine_kwargs: dict = {"pool_pre_ping": True}

# Connection-pool sizing only applies to a real pooled DB (Postgres/asyncpg).
# SQLite (used by the test suite) uses NullPool and rejects these kwargs.
if not settings.database_url.startswith("sqlite"):
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_async_engine(settings.database_url, **engine_kwargs)

# expire_on_commit=False prevents SQLAlchemy from expiring ORM attributes
# after a commit. With async sessions, accessing an expired attribute would
# trigger another DB round-trip outside the request context, causing errors.
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass
