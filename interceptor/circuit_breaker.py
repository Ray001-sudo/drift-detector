import time
import logging
from common.redis_client import get_redis_client
from common.redis_keys import CIRCUIT_BREAKER_STATE, CIRCUIT_BREAKER_FAILURES
from common.config import settings
import redis.asyncio as redis

logger = logging.getLogger(__name__)

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 30):
        self.service_name = settings.CIRCUIT_BREAKER_SERVICE_NAME
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state_key = CIRCUIT_BREAKER_STATE.format(service_name=self.service_name)
        self.count_key = CIRCUIT_BREAKER_FAILURES.format(service_name=self.service_name)
        self.time_key = f"circuit_breaker:{self.service_name}:last_failure_at"

    async def is_allowed(self) -> bool:
        try:
            r = await get_redis_client()
            # MGET to read all three keys at once
            state, count, last_failure = await r.mget(self.state_key, self.count_key, self.time_key)
            
            # If state key is missing (e.g. expired due to TTL), default it to half_open if last_failure exists
            if not state:
                if last_failure:
                    # TTL expired, transition to half_open
                    state = "half_open"
                    # Atomically update
                    async with r.pipeline(transaction=True) as pipe:
                        pipe.set(self.state_key, "half_open")
                        await pipe.execute()
                else:
                    state = "closed"
                    
            if state == "closed":
                return True
            if state == "open":
                return False
            if state == "half_open":
                # Allow one request to probe
                # To prevent all replicas probing at once, a real implementation might use a lock, 
                # but we just allow it if we see half_open.
                return True

            return True
        except Exception as e:
            logger.warning(f"Failed to read circuit breaker state, failing open: {e}")
            return True # Fail open

    async def record_failure(self) -> None:
        try:
            r = await get_redis_client()
            now = time.time()
            
            # Watch keys for optimistic locking could be used, but since we just increment, a pipeline works
            # We want to increment count, update last_failure. If count >= threshold, open.
            count = await r.incr(self.count_key)
            
            async with r.pipeline(transaction=True) as pipe:
                pipe.set(self.time_key, str(now))
                if count >= self.failure_threshold:
                    # Open the breaker, set TTL on state_key
                    pipe.set(self.state_key, "open", ex=self.recovery_timeout)
                    logger.warning(f"Circuit breaker opened for {self.service_name}")
                await pipe.execute()
        except Exception as e:
            logger.error(f"Failed to record circuit breaker failure: {e}")

    async def record_success(self) -> None:
        try:
            r = await get_redis_client()
            state = await r.get(self.state_key)
            
            if state == "half_open":
                # Close the breaker and reset
                async with r.pipeline(transaction=True) as pipe:
                    pipe.set(self.state_key, "closed")
                    pipe.set(self.count_key, 0)
                    pipe.delete(self.time_key)
                    await pipe.execute()
                logger.info(f"Circuit breaker closed for {self.service_name}")
            else:
                # In closed state, ensure count is 0 if it was positive
                # This could be optimised, but resetting on success is standard
                await r.set(self.count_key, 0)
        except Exception as e:
            logger.error(f"Failed to record circuit breaker success: {e}")
