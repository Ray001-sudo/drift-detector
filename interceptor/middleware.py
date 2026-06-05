import json
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import ValidationError
from common.schemas import FeatureVector
from common.kafka_client import get_kafka_producer
from interceptor.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

class DriftInterceptorMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Callable, model_version: str):
        super().__init__(app)
        self.producer = get_kafka_producer()
        self.circuit_breaker = CircuitBreaker()
        self.model_version = model_version
        self.producer_started = False

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.producer_started:
            try:
                await self.producer.start()
                self.producer_started = True
            except Exception as e:
                logger.error(f"Failed to start Kafka producer: {e}")

        # Capture raw request body
        try:
            body = await request.json()
        except Exception:
            body = None

        response = await call_next(request)

        # Non-blocking async drift feature publishing
        if body and "features" in body and "request_id" in body:
            # We don't block the response. We could spawn a background task.
            from fastapi import BackgroundTasks
            bg_tasks = BackgroundTasks()
            
            # Pass the app state registrar to publish_features
            registrar = getattr(request.app.state, "baseline_registrar", None)
            bg_tasks.add_task(self.publish_features, body, registrar)
            
            # Add background tasks to response
            response.background = bg_tasks

        return response

    async def publish_features(self, body: dict, registrar: 'BaselineRegistrar' = None) -> None:
        is_allowed = await self.circuit_breaker.is_allowed()
        if not is_allowed:
            return

        try:
            # Validate schema
            fv = FeatureVector(
                request_id=body["request_id"],
                model_version=self.model_version,
                features=body["features"]
            )
            
            if not self.producer_started:
                await self.producer.start()
                self.producer_started = True

            await self.producer.send_and_wait(
                "inference.features",
                fv.model_dump() # Pydantic v2
            )
            await self.circuit_breaker.record_success()
            
            if registrar:
                for f_name, f_val in fv.features.items():
                    # Expected Redis round-trip latency < 1ms on local docker network
                    # Max expected p99 added latency < 5ms for slow path
                    await registrar.observe(self.model_version, f_name, f_val)
                    
        except ValidationError as e:
            logger.error(f"Schema validation failed: {e}")
            # Do not record failure for schema validation
        except Exception as e:
            logger.error(f"Failed to publish to Kafka: {e}")
            await self.circuit_breaker.record_failure()
            
            # Dead letter queue logic - attempt once
            if self.producer_started:
                try:
                    await self.producer.send_and_wait(
                        "inference.features.dlq",
                        {"error": str(e), "payload": body}
                    )
                except Exception as dlq_e:
                    logger.error(f"Failed to publish to DLQ: {dlq_e}")
