from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, AnyHttpUrl, PostgresDsn, RedisDsn

class Settings(BaseSettings):
    # Database
    DATABASE_URL: PostgresDsn
    
    # Redis
    REDIS_URL: RedisDsn
    
    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str
    KAFKA_SECURITY_PROTOCOL: str
    KAFKA_SASL_MECHANISM: str = ""
    KAFKA_SASL_USERNAME: str = ""
    KAFKA_SASL_PASSWORD: str = ""
    KAFKA_SASL_ENABLED: bool = True
    
    # Security & Auth
    JWT_SECRET_KEY: SecretStr
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 8
    ALLOWED_ORIGINS: str
    
    # Alerts
    SLACK_WEBHOOK_URL: str
    PAGERDUTY_ROUTING_KEY: SecretStr
    
    # General Config
    ENVIRONMENT: str = "development"
    DASHBOARD_HOST: str = "localhost"
    LOG_LEVEL: str = "INFO"
    
    # Application Specific
    CIRCUIT_BREAKER_SERVICE_NAME: str = "drift_interceptor"
    MODEL_VERSION: str = "v1.0.0"
    BASELINE_WARMUP_MIN_SAMPLES: int = 500
    GRAFANA_ADMIN_PASSWORD: str = "adminadmin123"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

settings = Settings()
