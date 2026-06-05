from fastapi import APIRouter, Depends, Request, Query, HTTPException, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from common.database import get_db_session
from common.models import DriftScoreEvent, Alert, User
from common.config import settings
from dashboard.middleware import limiter
import jwt

router = APIRouter(prefix="/api/v1/drift", tags=["drift"])

async def get_current_user(request: Request, session: AsyncSession = Depends(get_db_session)):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth_header.split(" ")[1]
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY.get_secret_value(), algorithms=[settings.JWT_ALGORITHM])
        username: str = payload.get("sub") # type: ignore
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    stmt = select(User).where(User.username == username)
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user

@router.get("/scores")
@limiter.limit("100/minute")
async def get_scores(
    request: Request,
    feature_name: Optional[str] = None,
    detector_type: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user)
):
    stmt = select(DriftScoreEvent).order_by(desc(DriftScoreEvent.created_at)).limit(limit).offset(offset)
    if feature_name:
        stmt = stmt.where(DriftScoreEvent.feature_name == feature_name)
    if detector_type:
        stmt = stmt.where(DriftScoreEvent.detector_type == detector_type)
        
    result = await session.execute(stmt)
    scores = result.scalars().all()
    return scores

@router.get("/alerts")
@limiter.limit("100/minute")
async def get_alerts(
    request: Request,
    limit: int = Query(50, le=500),
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user)
):
    stmt = select(Alert).order_by(desc(Alert.fired_at)).limit(limit).offset(offset)
    result = await session.execute(stmt)
    alerts = result.scalars().all()
    return alerts
