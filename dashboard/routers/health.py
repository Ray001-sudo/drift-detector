from fastapi import APIRouter, Depends
from sqlalchemy import text
from common.database import get_db_session
from sqlalchemy.ext.asyncio import AsyncSession
from common.redis_client import get_redis_client

router = APIRouter(prefix="/api/v1/health", tags=["health"])

@router.get("")
async def health_check(session: AsyncSession = Depends(get_db_session)):
    db_ok = False
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    redis_ok = False
    try:
        r = await get_redis_client()
        await r.ping()
        redis_ok = True
    except Exception:
        pass
        
    status = "up" if db_ok and redis_ok else "down"
    
    return {
        "status": status,
        "database": "up" if db_ok else "down",
        "redis": "up" if redis_ok else "down"
    }
