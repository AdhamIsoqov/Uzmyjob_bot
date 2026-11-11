"""SQLAlchemy async base."""
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from uzmyjob.config import settings

engine = create_async_engine(settings.postgres_url, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    pass


async def get_session():
    async with AsyncSessionLocal() as session:
        yield session
