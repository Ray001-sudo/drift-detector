import pytest
import pytest_asyncio

# We'll test auth helper functions here
from common.security import get_password_hash, verify_password, create_access_token
import jwt
from common.config import settings

def test_password_hashing():
    pwd = "TestPassword123!"
    hashed = get_password_hash(pwd)
    assert hashed != pwd
    assert verify_password(pwd, hashed)
    assert not verify_password("wrong", hashed)

def test_jwt_creation():
    token = create_access_token({"sub": "admin", "role": "admin"})
    payload = jwt.decode(token, settings.JWT_SECRET_KEY.get_secret_value(), algorithms=[settings.JWT_ALGORITHM])
    assert payload["sub"] == "admin"
    assert payload["role"] == "admin"
    assert "exp" in payload
