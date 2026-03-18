"""Test fixtures shared across test modules."""

import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.db.base import Base
from app.main import create_app

# Use a separate test database URL (defaults to SQLite for simplicity)
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "sqlite+aiosqlite:///./test.db",
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create a test database engine and initialize tables."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def test_session_factory(test_engine):
    """Create a session factory bound to the test engine."""
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    return factory


@pytest_asyncio.fixture
async def test_db(test_session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session with automatic cleanup."""
    async with test_session_factory() as session:
        yield session
        # Rollback any uncommitted changes after each test
        await session.rollback()


@pytest_asyncio.fixture
async def app(test_session_factory, test_engine):
    """Create test application with test database."""
    application = create_app()

    # Override the session factory with test database
    application.state.session_factory = test_session_factory

    yield application


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def api_key(client: AsyncClient) -> str:
    resp = await client.post("/api/v1/agents", json={"name": "test-agent"})
    assert resp.status_code == 201
    return resp.json()["api_key"]
