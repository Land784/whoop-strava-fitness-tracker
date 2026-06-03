"""Shared test fixtures.

We use a separate in-memory SQLite database (via aiosqlite) for tests so
each test run is isolated and we don't need a running Postgres. The pattern:

  1. Create all tables fresh for the test session.
  2. Yield a session bound to that DB.
  3. Override FastAPI's get_db dependency to use the test session.
  4. Drop all tables after the session ends.

Every fixture marked `async` needs `@pytest.mark.asyncio` or the
`asyncio_mode = "auto"` setting in pytest.ini / pyproject.toml.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.security import create_access_token, hash_password
from app.dependencies import get_db
from app.main import app
from app.models.user import User

# aiosqlite gives us a file-less async SQLite DB for fast, isolated tests.
# Use a unique path so parallel test runs don't collide.
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"


@pytest_asyncio.fixture
async def engine():
    # Function-scoped: drop + recreate all tables for every test so committed
    # rows from one test can't leak into the next (e.g. the test user's email).
    _engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    await _engine.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncSession:
    """Yield a clean session for each test and roll back after."""
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        # Roll back any uncommitted changes so tests don't bleed into each other
        await session.rollback()


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncClient:
    """HTTP test client with get_db overridden to use the test session."""
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    """A persisted test user."""
    u = User(email="test@example.com", hashed_password=hash_password("password123"))
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
def auth_headers(user: User) -> dict[str, str]:
    """Bearer token headers for the test user."""
    token = create_access_token(str(user.id))
    return {"Authorization": f"Bearer {token}"}
