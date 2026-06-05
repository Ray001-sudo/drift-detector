from fastapi import APIRouter, Depends, Request, Query, HTTPException, status
from sqlalchemy import select, desc, func, distinct, case, and_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime
from common.database import get_db_session
from common.models import DriftScoreEvent, Alert, AlertRule, FeatureBaseline, User
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
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ---------------------------------------------------------------------------
# 1. GET /scores – paginated drift score events with optional filters
# ---------------------------------------------------------------------------
@router.get("/scores")
@limiter.limit("100/minute")
async def get_scores(
    request: Request,
    feature_name: Optional[str] = None,
    detector_type: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    try:
        stmt = select(DriftScoreEvent)
        if feature_name:
            stmt = stmt.where(DriftScoreEvent.feature_name == feature_name)
        if detector_type:
            stmt = stmt.where(DriftScoreEvent.detector_type == detector_type)
        stmt = stmt.order_by(desc(DriftScoreEvent.created_at)).limit(limit).offset(offset)

        result = await session.execute(stmt)
        scores = result.scalars().all()

        return [
            {
                "id": str(s.id),
                "window_id": s.window_id,
                "feature_name": s.feature_name,
                "detector_type": s.detector_type,
                "score": s.score,
                "is_drifted": s.is_drifted,
                "model_version": s.model_version,
                "window_start": str(s.window_start),
                "window_end": str(s.window_end),
                "sample_count": s.sample_count,
                "metadata": s.metadata_,
                "created_at": str(s.created_at),
            }
            for s in scores
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch drift scores: {e}")


# ---------------------------------------------------------------------------
# 2. GET /alerts – paginated alerts with optional severity filter
# ---------------------------------------------------------------------------
@router.get("/alerts")
@limiter.limit("100/minute")
async def get_alerts(
    request: Request,
    severity: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    try:
        stmt = select(Alert)
        if severity:
            stmt = stmt.where(Alert.severity == severity)
        stmt = stmt.order_by(desc(Alert.fired_at)).limit(limit).offset(offset)

        result = await session.execute(stmt)
        alerts = result.scalars().all()

        return [
            {
                "id": str(a.id),
                "rule_id": str(a.rule_id),
                "feature_name": a.feature_name,
                "detector_type": a.detector_type,
                "score": a.score,
                "threshold": a.threshold,
                "severity": a.severity,
                "model_version": a.model_version,
                "window_id": a.window_id,
                "fired_at": str(a.fired_at),
                "resolved_at": str(a.resolved_at) if a.resolved_at else None,
                "suppressed": a.suppressed,
            }
            for a in alerts
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch alerts: {e}")


# ---------------------------------------------------------------------------
# 3. GET /summary – aggregated dashboard summary
# ---------------------------------------------------------------------------
@router.get("/summary")
@limiter.limit("100/minute")
async def get_summary(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    try:
        # Count distinct monitored features
        feature_count_result = await session.execute(
            select(func.count(distinct(DriftScoreEvent.feature_name)))
        )
        feature_count = feature_count_result.scalar() or 0

        # Find the latest window_id
        latest_window_result = await session.execute(
            select(DriftScoreEvent.window_id)
            .order_by(desc(DriftScoreEvent.created_at))
            .limit(1)
        )
        latest_window_id = latest_window_result.scalar_one_or_none()

        max_psi = None
        max_kl = None
        latest_mmd = None

        if latest_window_id:
            # Max PSI score in the latest window
            psi_result = await session.execute(
                select(func.max(DriftScoreEvent.score)).where(
                    and_(
                        DriftScoreEvent.window_id == latest_window_id,
                        DriftScoreEvent.detector_type == "psi",
                    )
                )
            )
            max_psi = psi_result.scalar()

            # Max KL score in the latest window
            kl_result = await session.execute(
                select(func.max(DriftScoreEvent.score)).where(
                    and_(
                        DriftScoreEvent.window_id == latest_window_id,
                        DriftScoreEvent.detector_type == "kl",
                    )
                )
            )
            max_kl = kl_result.scalar()

            # Latest MMD score in the latest window
            mmd_result = await session.execute(
                select(DriftScoreEvent.score)
                .where(
                    and_(
                        DriftScoreEvent.window_id == latest_window_id,
                        DriftScoreEvent.detector_type == "mmd",
                    )
                )
                .order_by(desc(DriftScoreEvent.created_at))
                .limit(1)
            )
            latest_mmd = mmd_result.scalar_one_or_none()

        # Total alerts count
        total_alerts_result = await session.execute(
            select(func.count(Alert.id))
        )
        total_alerts = total_alerts_result.scalar() or 0

        # Unresolved alerts count
        unresolved_alerts_result = await session.execute(
            select(func.count(Alert.id)).where(Alert.resolved_at.is_(None))
        )
        unresolved_alerts = unresolved_alerts_result.scalar() or 0

        # Latest created_at timestamp
        latest_ts_result = await session.execute(
            select(func.max(DriftScoreEvent.created_at))
        )
        latest_timestamp = latest_ts_result.scalar()

        return {
            "feature_count": feature_count,
            "max_psi_score": max_psi,
            "max_kl_score": max_kl,
            "latest_mmd_score": latest_mmd,
            "total_alerts": total_alerts,
            "unresolved_alerts": unresolved_alerts,
            "latest_timestamp": str(latest_timestamp) if latest_timestamp else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch summary: {e}")


# ---------------------------------------------------------------------------
# 4. GET /models – distinct model versions with metadata
# ---------------------------------------------------------------------------
@router.get("/models")
@limiter.limit("100/minute")
async def get_models(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    try:
        # Get all distinct model versions from drift events and baselines
        model_versions_result = await session.execute(
            select(distinct(DriftScoreEvent.model_version))
        )
        model_versions = [row[0] for row in model_versions_result.all()]

        models = []
        for mv in model_versions:
            # Count baselines for this model
            baseline_count_result = await session.execute(
                select(func.count(FeatureBaseline.id)).where(
                    FeatureBaseline.model_version == mv
                )
            )
            baseline_count = baseline_count_result.scalar() or 0

            # Latest drift event timestamp for this model
            latest_event_result = await session.execute(
                select(func.max(DriftScoreEvent.created_at)).where(
                    DriftScoreEvent.model_version == mv
                )
            )
            latest_event_ts = latest_event_result.scalar()

            # Check if any drift detected in the last window for this model
            last_window_result = await session.execute(
                select(DriftScoreEvent.window_id)
                .where(DriftScoreEvent.model_version == mv)
                .order_by(desc(DriftScoreEvent.created_at))
                .limit(1)
            )
            last_window_id = last_window_result.scalar_one_or_none()

            has_drift = False
            if last_window_id:
                drift_check_result = await session.execute(
                    select(func.count(DriftScoreEvent.id)).where(
                        and_(
                            DriftScoreEvent.model_version == mv,
                            DriftScoreEvent.window_id == last_window_id,
                            DriftScoreEvent.is_drifted.is_(True),
                        )
                    )
                )
                drift_count = drift_check_result.scalar() or 0
                has_drift = drift_count > 0

            models.append(
                {
                    "model_version": mv,
                    "baseline_count": baseline_count,
                    "latest_event_at": str(latest_event_ts) if latest_event_ts else None,
                    "has_drift_in_last_window": has_drift,
                }
            )

        return models
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch models: {e}")


# ---------------------------------------------------------------------------
# 5. GET /monitoring – time-series data grouped by detector type
# ---------------------------------------------------------------------------
@router.get("/monitoring")
@limiter.limit("100/minute")
async def get_monitoring(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    try:
        stmt = (
            select(DriftScoreEvent)
            .order_by(desc(DriftScoreEvent.created_at))
            .limit(100)
        )
        result = await session.execute(stmt)
        events = result.scalars().all()

        # Reverse so the final output is ASC by created_at
        events = list(reversed(events))

        grouped: dict = {"psi": [], "kl": [], "mmd": []}
        for e in events:
            entry = {
                "feature": e.feature_name,
                "score": e.score,
                "time": str(e.created_at),
            }
            if e.detector_type in grouped:
                grouped[e.detector_type].append(entry)

        return grouped
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch monitoring data: {e}")


# ---------------------------------------------------------------------------
# 6. GET /alerts/rules – list all alert rules
# ---------------------------------------------------------------------------
@router.get("/alerts/rules")
@limiter.limit("100/minute")
async def get_alert_rules(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    try:
        stmt = select(AlertRule)
        result = await session.execute(stmt)
        rules = result.scalars().all()

        return [
            {
                "id": str(r.id),
                "feature_name": r.feature_name,
                "detector_type": r.detector_type,
                "threshold": r.threshold,
                "severity": r.severity,
                "is_active": r.is_active,
                "updated_by": r.updated_by,
                "updated_at": str(r.updated_at),
            }
            for r in rules
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch alert rules: {e}")


# ---------------------------------------------------------------------------
# 7. PUT /alerts/rules/{rule_id} – update an alert rule
# ---------------------------------------------------------------------------
@router.put("/alerts/rules/{rule_id}")
@limiter.limit("30/minute")
async def update_alert_rule(
    request: Request,
    rule_id: str,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    threshold = body.get("threshold")
    severity = body.get("severity")

    if threshold is None or severity is None:
        raise HTTPException(
            status_code=400,
            detail="Both 'threshold' and 'severity' are required",
        )

    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="'threshold' must be a number")

    try:
        stmt = select(AlertRule).where(AlertRule.id == rule_id)
        result = await session.execute(stmt)
        rule = result.scalar_one_or_none()

        if rule is None:
            raise HTTPException(status_code=404, detail="Alert rule not found")

        rule.threshold = threshold
        rule.severity = severity
        rule.updated_by = user.username
        rule.updated_at = datetime.utcnow()

        await session.commit()
        await session.refresh(rule)

        return {
            "id": str(rule.id),
            "feature_name": rule.feature_name,
            "detector_type": rule.detector_type,
            "threshold": rule.threshold,
            "severity": rule.severity,
            "is_active": rule.is_active,
            "updated_by": rule.updated_by,
            "updated_at": str(rule.updated_at),
        }
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update alert rule: {e}")
