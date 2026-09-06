from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..config import settings
from . import models  # noqa

echo_engine = settings.env in ["local"]
engine: AsyncEngine = create_async_engine(settings.postgres_db_string, echo=echo_engine)


async def create_db_and_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SQLModelAsyncSession(engine) as session:
        yield session


@asynccontextmanager
async def session_context():
    async with SQLModelAsyncSession(engine) as session:
        yield session
