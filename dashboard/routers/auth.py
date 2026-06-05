from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from datetime import datetime
from common.database import get_db_session
from common.models import User, AuthAttempt
from common.security import verify_password, create_access_token
from dashboard.middleware import limiter
from sqlalchemy.ext.asyncio import AsyncSession

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
