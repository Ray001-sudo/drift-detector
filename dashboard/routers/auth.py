from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from datetime import datetime
from common.database import get_db_session
from common.models import User, AuthAttempt
from common.security import verify_password, create_access_token
from common.config import settings
from dashboard.middleware import limiter
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/token")
@limiter.limit("10/minute")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), session: AsyncSession = Depends(get_db_session)):
    stmt = select(User).where(User.username == form_data.username)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    client_ip = request.client.host if request.client else "unknown"

    if not user or not verify_password(form_data.password, user.password_hash):
        auth_attempt = AuthAttempt(username=form_data.username, ip_address=client_ip, success=False)
        session.add(auth_attempt)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_attempt = AuthAttempt(username=user.username, ip_address=client_ip, success=True)
    user.last_login_at = datetime.utcnow()
    session.add(auth_attempt)
    await session.commit()

    access_token = create_access_token(data={"sub": user.username, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
async def get_me(request: Request, session: AsyncSession = Depends(get_db_session)):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth_header.split(" ")[1]

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=[settings.JWT_ALGORITHM],
        )
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    stmt = select(User).where(User.username == username)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    return {
        "username": user.username,
        "role": user.role,
        "last_login_at": str(user.last_login_at) if user.last_login_at else None,
    }

