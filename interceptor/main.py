from typing import Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from interceptor.middleware import DriftInterceptorMiddleware
from interceptor.baseline_registrar import BaselineRegistrar
from common.logging_config import setup_logging
from common.config import settings

setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI): # type: ignore
    # Startup
    registrar = BaselineRegistrar()
    app.state.baseline_registrar = registrar
    await registrar.start()
    yield
    # Shutdown
    await registrar.stop()
    middleware = next((m for m in app.user_middleware if m.cls == DriftInterceptorMiddleware), None)
    if middleware and getattr(middleware.kwargs.get("app", middleware), "producer_started", False):
        # We can't cleanly access the instantiated middleware directly from app.user_middleware 
        # so relying on garbage collection or a global state for the producer shutdown is typical.
        pass

app = FastAPI(title="Inference API", lifespan=lifespan)

app.add_middleware(
    DriftInterceptorMiddleware,
    model_version=settings.MODEL_VERSION
)

class InferenceRequest(BaseModel):
    request_id: str
    features: dict[str, float]

@app.post("/api/v1/inference")
async def predict(request: InferenceRequest) -> Dict[str, Any]:
    # Dummy prediction endpoint
    return {"status": "ok", "prediction": 0.95}

@app.get("/api/v1/health")
async def health() -> Dict[str, str]:
    return {"status": "up"}
