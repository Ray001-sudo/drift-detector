import redis.asyncio as redis
from common.config import settings

# Shared global redis connection pool
redis_client = redis.from_url(
    str(settings.REDIS_URL),
    decode_responses=True
)

async def get_redis_client() -> redis.Redis: # type: ignore
    return redis_client
