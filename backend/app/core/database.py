from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# create_async_engine uses asyncpg under the hood.
# pool_pre_ping sends a cheap "SELECT 1" before each checkout to detect
# stale connections — important in Docker where the DB can restart.
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

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
