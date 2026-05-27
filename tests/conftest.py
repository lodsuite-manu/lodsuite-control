"""Pytest configuration and fixtures."""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.db.models import Base
from app.db.database import get_session


# Test database URL (in-memory SQLite)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(test_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client with database override."""

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield test_session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def sample_briefing() -> str:
    """Sample briefing text for tests."""
    return "Software für Maschinenwartung. Zielgruppe: KMU-Geschäftsführer. Kernbotschaft: Digitalisierung ist kein Luxus mehr."


@pytest.fixture
def sample_yaml_script() -> str:
    """Sample YAML script for tests."""
    return """
title: "Test Video"
aspect_ratio: "9:16"
character: "markus_industrial"
scenes:
  - order: 1
    duration: 5
    location: warehouse_modern
    camera: selfie_pov_arm_visible
    action: talking_to_camera_confident
    voiceover: "POV: Du leitest 2026 ein Unternehmen."
    lipsync: true
    caption: "POV: Industrie 2026"
  - order: 2
    duration: 5
    location: office_glass_wall
    camera: medium_shot
    action: pointing_at_screen
    voiceover: "Während deine Konkurrenz noch Excel nutzt."
    lipsync: true
"""
