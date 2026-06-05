import asyncio
import logging
import json
import numpy as np
from datetime import datetime
from common.redis_client import get_redis_client
from common.redis_keys import BASELINE_WARMUP, BASELINE_REG_LOCK
from common.config import settings
from common.database import async_session_maker
from common.kafka_client import get_kafka_producer
from common.schemas import BaselineRegisteredEvent
from common.metrics import drift_baselines_auto_registered_total
from sqlalchemy import text

logger = logging.getLogger(__name__)

class BaselineRegistrar:
    def __init__(self):
        self._known_versions = set()
        self._refresh_task = None

    async def start(self):
        await self._refresh_known_versions()
        self._refresh_task = asyncio.create_task(self._refresh_loop())

    async def stop(self):
        if self._refresh_task:
            self._refresh_task.cancel()

    async def _refresh_loop(self):
        while True:
            await asyncio.sleep(300)
            await self._refresh_known_versions()

    async def _refresh_known_versions(self):
        try:
            async with async_session_maker() as session:
                # Assuming feature_baselines table has model_version column
                result = await session.execute(text("SELECT DISTINCT model_version FROM feature_baselines"))
                versions = {row[0] for row in result.all()}
                self._known_versions = versions
        except Exception as e:
            logger.error(f"Failed to refresh known baseline versions: {e}")

    async def observe(self, model_version: str, feature_name: str, value: float) -> None:
        if model_version in self._known_versions:
            return

        try:
            redis = await get_redis_client()
            warmup_key = BASELINE_WARMUP.format(model_version=model_version, feature_name=feature_name)
            
            # RPUSH to append
            await redis.rpush(warmup_key, value)
            
            # Use EXPIRE NX if available in aioredis/redis-py
            # If EXPIRE NX is not directly available, we can check TTL
            ttl = await redis.ttl(warmup_key)
            if ttl < 0:
                await redis.expire(warmup_key, 86400)

            length = await redis.llen(warmup_key)
            if length >= settings.BASELINE_WARMUP_MIN_SAMPLES:
                # Trigger registration logic in the background so we don't block the request longer than the Redis commands
                asyncio.create_task(self._register_baseline(model_version, feature_name))
        except Exception as e:
            logger.warning(f"Failed to observe feature for baseline warmup: {e}")

    async def _register_baseline(self, model_version: str, feature_name: str) -> None:
        try:
            redis = await get_redis_client()
            lock_key = BASELINE_REG_LOCK.format(model_version=model_version, feature_name=feature_name)
            
            # Acquire lock
            acquired = await redis.set(lock_key, "1", nx=True, ex=60)
            if not acquired:
                return

            warmup_key = BASELINE_WARMUP.format(model_version=model_version, feature_name=feature_name)
            raw_data = await redis.lrange(warmup_key, 0, -1)
            if not raw_data:
                await redis.delete(lock_key)
                return

            # Convert to float64 numpy array
            arr = np.array([float(x) for x in raw_data], dtype=np.float64)
            
            # Validate: no NaN, no Inf
            if np.isnan(arr).any() or np.isinf(arr).any():
                logger.warning(f"Bad data in warmup buffer for {feature_name} {model_version}. Discarding.")
                await redis.delete(warmup_key, lock_key)
                return
                
            sample_count = len(arr)
            
            async with async_session_maker() as session:
                # Check if baseline exists
                exists_stmt = text("SELECT 1 FROM feature_baselines WHERE model_version = :mv AND feature_name = :fn")
                result = await session.execute(exists_stmt, {"mv": model_version, "fn": feature_name})
                if result.scalar_one_or_none() is not None:
                    logger.info(f"Baseline already exists for {feature_name} {model_version}. Not overwriting.")
                    await redis.delete(warmup_key, lock_key)
                    return
                
                # Insert
                insert_stmt = text("""
                    INSERT INTO feature_baselines 
                    (feature_name, model_version, raw_samples, sample_count, computed_at, created_by) 
                    VALUES (:fn, :mv, :samples, :count, :computed, :creator)
                """)
                # Assuming raw_samples is stored as JSONB list or string
                await session.execute(insert_stmt, {
                    "fn": feature_name,
                    "mv": model_version,
                    "samples": json.dumps(arr.tolist()),
                    "count": sample_count,
                    "computed": datetime.utcnow(),
                    "creator": "interceptor/auto"
                })
                await session.commit()
                
            self._known_versions.add(model_version)
            
            logger.info(f"Auto-registered baseline for feature '{feature_name}' model version '{model_version}' from {sample_count} live samples")
            drift_baselines_auto_registered_total.labels(model_version=model_version, feature_name=feature_name).inc()
            
            await redis.delete(warmup_key, lock_key)
            
            producer = get_kafka_producer()
            # Ensure producer is started
            await producer.start()
            
            event = BaselineRegisteredEvent(
                model_version=model_version,
                feature_name=feature_name,
                sample_count=sample_count,
                registered_at=datetime.utcnow(),
                registered_by="interceptor/auto"
            )
            await producer.send_and_wait("baseline.registered", event.model_dump(mode="json"))

        except Exception as e:
            logger.error(f"Failed to auto-register baseline for {feature_name} {model_version}: {e}")
            # Do not delete warmup key on general failure so it can be retried, but delete lock
            try:
                redis = await get_redis_client()
                await redis.delete(BASELINE_REG_LOCK.format(model_version=model_version, feature_name=feature_name))
            except Exception:
                pass
