import json
import ssl  # Added native SSL utility module
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer # type: ignore
from common.config import settings
from typing import Any

def get_kafka_producer() -> AIOKafkaProducer:
    config: dict[str, Any] = {
        "bootstrap_servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "value_serializer": lambda v: json.dumps(v).encode("utf-8"),
        "acks": "all",
        "retry_backoff_ms": 100,
    }
    
    if settings.KAFKA_SASL_ENABLED:
        config.update({
            "security_protocol": settings.KAFKA_SECURITY_PROTOCOL,
            "sasl_mechanism": settings.KAFKA_SASL_MECHANISM,
            "sasl_plain_username": settings.KAFKA_SASL_USERNAME,
            "sasl_plain_password": settings.KAFKA_SASL_PASSWORD,
        })
        
        # Inject default certificate processing context for SASL_SSL or SSL connections
        if "SSL" in settings.KAFKA_SECURITY_PROTOCOL:
            config["ssl_context"] = ssl.create_default_context()
        
    return AIOKafkaProducer(**config)

def get_kafka_consumer(topic: str, group_id: str) -> AIOKafkaConsumer:
    config: dict[str, Any] = {
        "bootstrap_servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "group_id": group_id,
        "value_deserializer": lambda v: json.loads(v.decode("utf-8")),
        "auto_offset_reset": "earliest",
        "enable_auto_commit": False,
    }
    
    if settings.KAFKA_SASL_ENABLED:
        config.update({
            "security_protocol": settings.KAFKA_SECURITY_PROTOCOL,
            "sasl_mechanism": settings.KAFKA_SASL_MECHANISM,
            "sasl_plain_username": settings.KAFKA_SASL_USERNAME,
            "sasl_plain_password": settings.KAFKA_SASL_PASSWORD,
        })
        
        # Inject default certificate processing context for SASL_SSL or SSL connections
        if "SSL" in settings.KAFKA_SECURITY_PROTOCOL:
            config["ssl_context"] = ssl.create_default_context()
        
    return AIOKafkaConsumer(topic, **config)