import jwt
import logging
import sys
from datetime import datetime, timedelta
from passlib.context import CryptContext
from common.config import settings

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY.get_secret_value(), algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

def validate_secrets() -> None:
    required_secrets = [
        "JWT_SECRET_KEY",
        "DATABASE_URL",
        "REDIS_URL"
    ]
    missing = []
    
    if not getattr(settings, "JWT_SECRET_KEY", None) or not settings.JWT_SECRET_KEY.get_secret_value():
         missing.append("JWT_SECRET_KEY")
         
    if not getattr(settings, "DATABASE_URL", None):
        missing.append("DATABASE_URL")
        
    if not getattr(settings, "REDIS_URL", None):
        missing.append("REDIS_URL")

    if missing:
        logger.error(f"Missing required secrets: {', '.join(missing)}")
        sys.exit(1)

if __name__ == "__main__":
    validate_secrets()
    print("Secrets validation passed.")
