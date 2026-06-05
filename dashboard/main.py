import asyncio
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from common.config import settings
from common.kafka_client import get_kafka_consumer
from common.redis_client import get_redis_client
from common.logging_config import setup_logging
from dashboard.middleware import setup_middleware, limiter
from dashboard.routers import auth, drift, health
from dashboard.websocket_manager import manager
import jwt

setup_logging()
logger = logging.getLogger(__name__)

async def consume_alerts_and_broadcast() -> None:
    consumer = get_kafka_consumer("drift.alerts", "dashboard-group")
    try:
        await consumer.start()
        async for msg in consumer:
            if msg.value:
                # We expect the payload to be dictionary, broadcast it
                await manager.broadcast({"type": "alert", "data": msg.value})
    except Exception as e:
        logger.error(f"Kafka consumer error: {e}")
    finally:
        await consumer.stop()

async def consume_scores_and_broadcast() -> None:
    consumer = get_kafka_consumer("drift.scores", "dashboard-scores-group")
    try:
        await consumer.start()
        async for msg in consumer:
            if msg.value:
                await manager.broadcast({"type": "score", "data": msg.value})
    except Exception as e:
        logger.error(f"Kafka scores consumer error: {e}")
    finally:
        await consumer.stop()

@asynccontextmanager
async def lifespan(app: FastAPI): # type: ignore
    # Configure slowapi with redis
    from slowapi.extension import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    
    # We must start background tasks for Kafka consuming
    t1 = asyncio.create_task(consume_alerts_and_broadcast())
    t2 = asyncio.create_task(consume_scores_and_broadcast())
    
    yield
    t1.cancel()
    t2.cancel()

app = FastAPI(title="Drift Dashboard", lifespan=lifespan)

setup_middleware(app)

app.include_router(auth.router)
app.include_router(drift.router)
app.include_router(health.router)

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    # Validate token
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY.get_secret_value(), algorithms=[settings.JWT_ALGORITHM])
        if not payload.get("sub"):
            await websocket.close(code=4401)
            return
    except jwt.PyJWTError:
        await websocket.close(code=4401)
        return

    client_ip = websocket.client.host if websocket.client else "unknown"
    # Basic IP connection limit could be checked here in manager
    
    connected = await manager.connect(websocket)
    if not connected:
        return

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "pong":
                    manager.unresponsive_counts[websocket] = 0
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
        await manager.disconnect(websocket)

# Mount static files for the frontend
app.mount("/", StaticFiles(directory="dashboard/static", html=True), name="static")
