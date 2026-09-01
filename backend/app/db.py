"""Async Postgres access: pgvector-aware connection pool."""

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from pgvector.psycopg import register_vector_async

from app.config import config

_pool: AsyncConnectionPool | None = None


async def _configure_connection(conn: AsyncConnection) -> None:
    # Runs for every connection the pool creates, so Vector params/results
    # adapt correctly on all of them.
    await register_vector_async(conn)


async def create_pool() -> AsyncConnectionPool:
    pool = AsyncConnectionPool(
        conninfo=config.DATABASE_URL,
        min_size=1,
        max_size=5,
        open=False,
        configure=_configure_connection,
    )
    await pool.open(wait=True, timeout=10.0)
    return pool


async def get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = await create_pool()
    return _pool
