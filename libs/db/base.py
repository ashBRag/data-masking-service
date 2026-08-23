"""Reusable async SQLAlchemy/SQLModel database wiring.

Generic and reusable: `Database` takes a `DatabaseSettings` value object
instead of importing any project's settings class, so it can be reused
as-is in another project.

Usage in a project's own `services/database.py` (or directly in `main.py`):

    from libs.db import Database, DatabaseSettings

    db = Database(DatabaseSettings(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        database=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        pool_size=settings.POSTGRES_POOL_SIZE,
        max_overflow=settings.POSTGRES_MAX_OVERFLOW,
    ))

    # in the FastAPI lifespan:
    await db.connect()
    ...
    await db.disconnect()

    # as a route dependency:
    async def endpoint(session: AsyncSession = Depends(db.get_session)): ...
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

import uuid_utils
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import Field, SQLModel


class TimestampedModel(SQLModel):
    """SQLModel base that stamps every row with its creation time (UTC)."""

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def uuid7() -> uuid.UUID:
    """Generate a time-ordered (UUIDv7) primary key value.

    Prefer this over `uuid.uuid4` for primary keys: UUIDv7's first 48 bits
    are a millisecond Unix timestamp, so IDs sort roughly by creation time.
    That keeps new rows appending near the "hot" edge of a B-tree PK/FK
    index instead of scattering across it at random (as uuid4 does), which
    otherwise causes index bloat and worse cache locality as a table grows -
    while still keeping IDs non-sequential/non-enumerable and generatable
    client-side with no DB round-trip, unlike a plain auto-increment integer.

    `uuid_utils.uuid7()` returns its own UUID type, not stdlib `uuid.UUID`,
    so this converts it - SQLAlchemy's UUID column type expects the stdlib one.
    """
    return uuid.UUID(str(uuid_utils.uuid7()))


@dataclass(frozen=True)
class DatabaseSettings:
    """Connection parameters for a Postgres database.

    A plain value object (not a pydantic BaseSettings) so libs/db has zero
    dependency on any particular settings/config library - the caller reads
    these values from wherever it likes and passes them in.
    """

    host: str
    port: int
    database: str
    user: str
    password: str
    pool_size: int = 5
    max_overflow: int = 10

    def to_url(self) -> str:
        """Build a psycopg3 async SQLAlchemy URL from these settings."""
        return f"postgresql+psycopg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class Database:
    """Owns the async engine + session factory for one database.

    Kept as a class (rather than module-level globals) so a project can
    instantiate more than one Database if it ever needs to talk to two
    different Postgres instances.
    """

    def __init__(self, settings: DatabaseSettings):
        """Build the async engine eagerly; no network call happens until first use."""
        self._settings = settings
        self.engine: AsyncEngine = create_async_engine(
            settings.to_url(),
            pool_size=settings.pool_size,
            max_overflow=settings.max_overflow,
            pool_pre_ping=True,  # detects/recycles dead connections (e.g. after a DB restart)
        )
        self._session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def connect(self) -> None:
        """Verify connectivity at startup so config mistakes fail fast, not on first request."""
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def disconnect(self) -> None:
        """Dispose of the connection pool (call this on app shutdown)."""
        await self.engine.dispose()

    async def get_session(self) -> AsyncIterator[AsyncSession]:
        """FastAPI dependency: yields a session, always closing it afterwards.

        Usage: `session: AsyncSession = Depends(db.get_session)`
        """
        async with self._session_factory() as session:
            yield session

    async def health_check(self) -> bool:
        """Return True if a trivial query succeeds, False on any error.

        Used by /health so it never raises - a DB outage should degrade the
        health response, not crash the health endpoint itself.
        """
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
