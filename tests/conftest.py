"""Test fixtures and configuration."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from taskflow.models.base import Base
from taskflow.core.config import Settings, get_settings


@pytest.fixture(scope="session")
def test_settings():
    """Override settings for testing."""
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        celery_task_always_eager=True,
        scheduler_enabled=False,
    )


@pytest_asyncio.fixture
async def db_session(test_settings):
    """Create test database session."""
    engine = create_async_engine(
        str(test_settings.database_url),
        echo=False,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with AsyncSessionLocal() as session:
        yield session
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest_asyncio.fixture
async def task_service(db_session):
    """Get task service instance."""
    from taskflow.services.task_service import TaskService
    return TaskService(db_session)
