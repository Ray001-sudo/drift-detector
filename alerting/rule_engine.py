import ssl
import faust
import logging
from typing import Dict, Any
from sqlalchemy import select, update
from common.config import settings
from common.database import async_session_maker
from common.models import AlertRule, Alert, DriftScoreEvent
from common.redis_client import get_redis_client
from common.metrics import drift_alerts_fired_total, drift_alerts_suppressed_total
from common.redis_keys import ALERT_DEDUP
from alerting.slack_notifier import send_slack_alert
from alerting.pagerduty_notifier import send_pagerduty_alert
from reference_store.store import store as ref_store
import json

logger = logging.getLogger(__name__)

broker_url = settings.KAFKA_BOOTSTRAP_SERVERS

# 1. Build the SSL context and PUT BACK the bypass hacks.
# The container lacks the CA bundle, so we absolutely need this to connect to Aiven.
ctx = None
if settings.KAFKA_SASL_ENABLED and "SSL" in settings.KAFKA_SECURITY_PROTOCOL:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

# 2. Build the SASL Credentials and inject the SSL context
broker_credentials = None
if settings.KAFKA_SASL_ENABLED:
    broker_credentials = faust.SASLCredentials(
        username=settings.KAFKA_SASL_USERNAME,
        password=settings.KAFKA_SASL_PASSWORD,
        mechanism=settings.KAFKA_SASL_MECHANISM or "PLAIN",
        ssl_context=ctx
    )

# 3. Initialize the Faust App cleanly
app = faust.App(
    'drift-alerter',
    broker=f"kafka://{broker_url}",
    broker_credentials=broker_credentials,
    datadir='/tmp/drift-alerter-data',
    topic_allow_declare=False  # <-- THE MAGIC FIX: Stops Aiven from dropping the connection!
)

scores_topic = app.topic('drift.scores', value_type=dict)
alerts_topic = app.topic('drift.alerts', value_type=dict)
baseline_registered_topic = app.topic('baseline.registered', value_type=dict)

# In-memory rule cache
# Refreshed every 60s
rules_cache: Dict[str, Any] = {}

@app.timer(interval=60.0)
async def refresh_rules() -> None:
    global rules_cache
    try:
        async with async_session_maker() as session:
            stmt = select(AlertRule).where(AlertRule.is_active == True)
            result = await session.execute(stmt)
            active_rules = result.scalars().all()
            
            new_cache = {}
            for r in active_rules:
                key = f"{r.feature_name}_{r.detector_type}" if r.feature_name else f"global_{r.detector_type}"
                if key not in new_cache:
                    new_cache[key] = []
                new_cache[key].append({
                    "id": str(r.id),
                    "threshold": r.threshold,
                    "severity": r.severity
                })
            rules_cache = new_cache
            logger.info(f"Refreshed {len(active_rules)} alert rules.")
    except Exception as e:
        logger.error(f"Failed to refresh alert rules: {e}")

async def evaluate_drift_event(event: dict) -> None:
    feature_name = event['feature_name']
    detector_type = event['detector_type']
    score = event['score']
    is_drifted = event['is_drifted']
    model_version = event['model_version']
    
    # Store event in DB first
    try:
        async with async_session_maker() as session:
            db_event = DriftScoreEvent(
                window_id=event['window_id'],
                feature_name=feature_name,
                detector_type=detector_type,
                score=score,
                is_drifted=is_drifted,
                model_version=model_version,
                window_start=event['window_start'],
                window_end=event['window_end'],
                sample_count=event['sample_count'],
                metadata_=event.get('metadata')
            )
            session.add(db_event)
            await session.commit()
    except Exception as e:
        logger.error(f"Failed to persist DriftScoreEvent: {e}")

    # Check rules
    specific_key = f"{feature_name}_{detector_type}"
    global_key = f"global_{detector_type}"
    
    applicable_rules = rules_cache.get(specific_key, []) + rules_cache.get(global_key, [])
    
    if not is_drifted and score < 0.1: # Auto-resolve logic
        try:
            r = await get_redis_client()
            dedup_key = ALERT_DEDUP.format(feature_name=feature_name, detector_type=detector_type)
            await r.delete(dedup_key)
        except Exception as e:
            logger.error(f"Failed to auto-resolve / clear dedup key: {e}")
        return

    for rule in applicable_rules:
        if score >= rule['threshold']:
            await trigger_alert(event, rule)
            break

async def trigger_alert(event: dict, rule: dict) -> None:
    feature_name = event['feature_name']
    detector_type = event['detector_type']
    severity = rule['severity']
    
    # Deduplication using Redis SET NX EX
    r = await get_redis_client()
    dedup_key = ALERT_DEDUP.format(feature_name=feature_name, detector_type=detector_type)
    
    try:
        # 300 seconds = 5 minutes
        is_new = await r.set(dedup_key, str(event['window_id']), nx=True, ex=300)
    except Exception as e:
        logger.error(f"Redis unreachable when checking dedup for {dedup_key}. Failing open: {e}")
        is_new = True # Fail open!
        
    if not is_new:
        logger.debug(f"Suppressed duplicate alert for {feature_name} {detector_type}")
        drift_alerts_suppressed_total.labels(feature_name=feature_name, detector_type=detector_type).inc()
        return

    # Persist alert
    try:
        async with async_session_maker() as session:
            new_alert = Alert(
                rule_id=rule['id'],
                feature_name=feature_name,
                detector_type=detector_type,
                score=event['score'],
                threshold=rule['threshold'],
                severity=severity,
                model_version=event['model_version'],
                window_id=event['window_id']
            )
            session.add(new_alert)
            await session.commit()
            
        drift_alerts_fired_total.labels(feature_name=feature_name, detector_type=detector_type, severity=severity).inc()
        
        # Publish to Kafka
        await alerts_topic.send(value={
            "feature_name": feature_name,
            "detector_type": detector_type,
            "score": event['score'],
            "severity": severity
        })
        
        # Send Slack
        msg = f"*{severity.upper()} Drift Alert*\nFeature: {feature_name}\nDetector: {detector_type}\nScore: {event['score']:.4f} (Threshold: {rule['threshold']:.4f})\n<https://{settings.DASHBOARD_HOST}|View Dashboard>"
        await send_slack_alert(msg)
        
        # Send PagerDuty if critical
        is_pd_critical = False
        if detector_type == 'psi' and event['score'] > 0.35: is_pd_critical = True
        if detector_type == 'kl' and event['score'] > 0.30: is_pd_critical = True
        if detector_type == 'mmd' and event.get('metadata', {}).get('p_value', 1.0) < 0.01: is_pd_critical = True
            
        if severity == 'critical' and is_pd_critical:
            await send_pagerduty_alert(
                summary=f"Critical Drift on {feature_name}",
                source=f"drift-detector-{settings.ENVIRONMENT}",
            )
            
    except Exception as e:
        logger.error(f"Failed to trigger alert fully: {e}")

@app.agent(scores_topic)
async def process_scores(stream: faust.Stream) -> None: # type: ignore
    async for event in stream:
        await evaluate_drift_event(event)

@app.agent(baseline_registered_topic)
async def process_baseline_registration(stream: faust.Stream) -> None: # type: ignore
    async for event in stream:
        mv = event.get("model_version")
        fn = event.get("feature_name")
        if mv and fn:
            await ref_store.refresh_baseline(fn, mv)

def main() -> None:
    app.main()
