import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator
import asyncpg
from asyncpg import Connection, Pool

logger = logging.getLogger(__name__)


class DatabasePool:
    """A class that manages a connection pool to a PostgreSQL database using asyncpg."""

    _instance: "DatabasePool | None" = None
    _pool: Pool | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def connect(self, dsn: str , min_size: int = 5, max_size: int = 20) -> None:
        if self._pool is not None:
            logger.warning("Pool is already created.")
            return
        try:
        
            self._pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=min_size,
                max_size=max_size,
                command_timeout=60,
            )
            logger.info("Pool created succesfully")
        except Exception as e:
            logger.error(f"Error create the pool:{e}")
            raise

    async def disconnect(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("Pool disconnected succesfully")

    @property
    def pool(self) -> Pool:
        if self._pool is None:
            raise RuntimeError("Pool didnt connect yet,First open the connect")
        return self._pool


db = DatabasePool()


@asynccontextmanager
async def get_connection() -> AsyncIterator[Connection]:
    async with db.pool.acquire() as connection:
        yield connection



async def get_db() -> AsyncIterator[Connection]:
    async with db.pool.acquire() as connection:
        yield connection        
