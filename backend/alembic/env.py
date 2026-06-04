"""Alembic migration environment.

Alembic is a synchronous tool, but our app uses an async engine. The bridge
is `conn.run_sync(do_run_migrations)` — we open an async connection, then hand
it to Alembic's synchronous migration runner via run_sync. This way Alembic
drives the migrations while the underlying connection is still asyncpg.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

db_url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")

# Import every model module so Alembic can see them for --autogenerate.
# Missing an import here means Alembic won't detect that table's changes.
from app.core.database import Base  # noqa: E402
import app.models.user              # noqa: F401
import app.models.workout           # noqa: F401
import app.models.recovery          # noqa: F401
import app.models.training_plan     # noqa: F401
import app.models.daily_briefing     # noqa: F401

target_metadata = Base.metadata


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        # run_sync hands the real connection to the synchronous Alembic runner
        await conn.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
