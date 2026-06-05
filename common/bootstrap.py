import asyncio
import structlog
from common.database import engine
from common.models import Base

logger = structlog.get_logger(__name__)

async def _init_db() -> None:
    logger.info("Initializing database schema via SQLAlchemy metadata...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schema synchronized successfully.")
    except Exception as e:
        logger.error(f"Failed to synchronize database schema: {e}")
        raise
    finally:
        # Dispose the engine to close all connections from this temporary event loop.
        # This prevents "Event loop is closed" errors when Faust starts its own loop
        # and reuses the global engine variable.
        await engine.dispose()

def run_bootstrap() -> None:
    """Run all necessary pre-startup bootstrap tasks sequentially."""
    logger.info("Running pre-flight bootstrap sequence...")
    asyncio.run(_init_db())
    logger.info("Pre-flight bootstrap sequence complete.")
