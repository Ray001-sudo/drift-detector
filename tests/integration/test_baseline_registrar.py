import pytest
import asyncio
from datetime import datetime
import numpy as np
from sqlalchemy import text
from common.redis_client import get_redis_client
from common.redis_keys import BASELINE_WARMUP, BASELINE_REG_LOCK
from common.database import async_session_maker
from common.config import settings
from interceptor.baseline_registrar import BaselineRegistrar

@pytest.fixture
async def redis():
    r = await get_redis_client()
    yield r
    await r.flushdb()

@pytest.fixture
async def db_session():
    async with async_session_maker() as session:
        yield session

@pytest.fixture
async def clean_db():
    async with async_session_maker() as session:
        await session.execute(text("TRUNCATE TABLE feature_baselines RESTART IDENTITY CASCADE;"))
        await session.commit()

@pytest.fixture
async def registrar():
    reg = BaselineRegistrar()
    await reg.start()
    yield reg
    await reg.stop()

@pytest.mark.asyncio
async def test_baseline_registrar_warmup_accumulation(registrar, redis, clean_db):
    # Setup
    model_version = "v-test"
    feature_name = "f1"
    
    # Observe less than threshold
    for i in range(settings.BASELINE_WARMUP_MIN_SAMPLES - 1):
        await registrar.observe(model_version, feature_name, 1.0)
    
    # Wait briefly for background tasks (though we shouldn't have triggered registration yet)
    await asyncio.sleep(0.1)
    
    warmup_key = BASELINE_WARMUP.format(model_version=model_version, feature_name=feature_name)
    llen = await redis.llen(warmup_key)
    assert llen == settings.BASELINE_WARMUP_MIN_SAMPLES - 1
    
    # Observe one more to trigger threshold
    await registrar.observe(model_version, feature_name, 2.0)
    
    # Give the async background task time to run
    await asyncio.sleep(0.5)
    
    # Buffer and lock should be cleared
    llen = await redis.llen(warmup_key)
    assert llen == 0
    lock = await redis.get(BASELINE_REG_LOCK.format(model_version=model_version, feature_name=feature_name))
    assert lock is None

@pytest.mark.asyncio
async def test_baseline_registrar_inserts_to_db(registrar, db_session, redis, clean_db):
    model_version = "v-test-2"
    feature_name = "f2"
    
    for i in range(settings.BASELINE_WARMUP_MIN_SAMPLES):
        await registrar.observe(model_version, feature_name, float(i))
        
    await asyncio.sleep(0.5)
    
    stmt = text("SELECT sample_count FROM feature_baselines WHERE model_version = :mv AND feature_name = :fn")
    result = await db_session.execute(stmt, {"mv": model_version, "fn": feature_name})
    count = result.scalar_one_or_none()
    
    assert count == settings.BASELINE_WARMUP_MIN_SAMPLES

@pytest.mark.asyncio
async def test_baseline_registrar_fast_path(registrar, db_session, redis, clean_db):
    model_version = "v-test-3"
    feature_name = "f3"
    
    # Pre-populate memory
    registrar._known_versions.add(model_version)
    
    await registrar.observe(model_version, feature_name, 5.0)
    
    # Redis should not be touched
    warmup_key = BASELINE_WARMUP.format(model_version=model_version, feature_name=feature_name)
    llen = await redis.llen(warmup_key)
    assert llen == 0

@pytest.mark.asyncio
async def test_baseline_registrar_idempotent_registration(registrar, db_session, redis, clean_db):
    model_version = "v-test-4"
    feature_name = "f4"
    
    # Force DB insert
    async with async_session_maker() as s:
        await s.execute(text("""
            INSERT INTO feature_baselines (feature_name, model_version, raw_samples, sample_count, computed_at, created_by)
            VALUES (:fn, :mv, '[]', 0, :dt, 'test')
        """), {"fn": feature_name, "mv": model_version, "dt": datetime.utcnow()})
        await s.commit()
        
    # Trigger observe threshold
    for i in range(settings.BASELINE_WARMUP_MIN_SAMPLES):
        await registrar.observe(model_version, feature_name, 1.0)
        
    await asyncio.sleep(0.5)
    
    # Should not overwrite, but buffer should still be cleaned
    warmup_key = BASELINE_WARMUP.format(model_version=model_version, feature_name=feature_name)
    assert await redis.llen(warmup_key) == 0

@pytest.mark.asyncio
async def test_baseline_registrar_bad_data_discard(registrar, db_session, redis, clean_db):
    model_version = "v-test-5"
    feature_name = "f5"
    
    for i in range(settings.BASELINE_WARMUP_MIN_SAMPLES - 1):
        await registrar.observe(model_version, feature_name, 1.0)
        
    # Inject bad data (NaN) - Note: standard json doesn't support NaN natively in the same way, but float('nan') does
    await registrar.observe(model_version, feature_name, float('nan'))
    
    await asyncio.sleep(0.5)
    
    # Should discard and not insert
    stmt = text("SELECT sample_count FROM feature_baselines WHERE model_version = :mv AND feature_name = :fn")
    result = await db_session.execute(stmt, {"mv": model_version, "fn": feature_name})
    assert result.scalar_one_or_none() is None
    
    # Redis cleaned
    warmup_key = BASELINE_WARMUP.format(model_version=model_version, feature_name=feature_name)
    assert await redis.llen(warmup_key) == 0
