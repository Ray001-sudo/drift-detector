import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from common.models import Base
import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/0" # Mocked or handled in tests

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.fixture
async def db_session(db_engine):
    async_session = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()

@pytest.fixture(scope="session")
def kafka_container():
    from testcontainers.kafka import KafkaContainer # type: ignore
    with KafkaContainer("confluentinc/cp-kafka:7.5.0") as kafka:
        # yield the bootstrap server
        yield kafka.get_bootstrap_server()

@pytest.fixture
def kafka_topics():
    import uuid
    topic_id = str(uuid.uuid4())[:8]
    return {
        "features": f"inference.features.{topic_id}",
        "scores": f"drift.scores.{topic_id}",
        "alerts": f"drift.alerts.{topic_id}"
    }
