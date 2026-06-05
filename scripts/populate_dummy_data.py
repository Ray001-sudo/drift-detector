import asyncio
import os
import uuid
from datetime import datetime, timedelta
import random

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from common.models import DriftScoreEvent, Alert, AlertRule
from common.config import settings

async def main():
    engine = create_async_engine(str(settings.DATABASE_URL), echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    print("Connecting to database to insert synthetic drift events...")
    
    features = ["age", "income", "credit_score", "tenure"]
    detectors = ["kl", "psi", "mmd"]
    now = datetime.utcnow()
    
    events_to_add = []
    alerts_to_add = []
    
    async with async_session() as session:
        # Get or create a dummy rule for foreign key constraint
        stmt = select(AlertRule).limit(1)
        rule = (await session.execute(stmt)).scalar_one_or_none()
        if not rule:
            rule = AlertRule(
                id=str(uuid.uuid4()),
                feature_name="age",
                detector_type="psi",
                threshold=0.20,
                severity="critical"
            )
            session.add(rule)
            await session.commit()
            
        # Generate 150 historical drift events over the last 24 hours
        for i in range(150):
            timestamp = now - timedelta(hours=24) + timedelta(minutes=random.randint(0, 1400))
            feat = random.choice(features)
            detector = random.choice(detectors)
            score = random.uniform(0.01, 0.45) if detector != "mmd" else random.uniform(0.01, 0.99)
            is_drifted = (detector == "kl" and score > 0.15) or \
                         (detector == "psi" and score > 0.20) or \
                         (detector == "mmd" and score < 0.05)
            
            event = DriftScoreEvent(
                id=str(uuid.uuid4()),
                window_id=str(uuid.uuid4())[:8],
                feature_name=feat,
                detector_type=detector,
                score=score,
                is_drifted=is_drifted,
                model_version=settings.MODEL_VERSION,
                window_start=timestamp - timedelta(seconds=60),
                window_end=timestamp,
                sample_count=1000,
                created_at=timestamp
            )
            events_to_add.append(event)
            
            if is_drifted and random.random() > 0.5:
                alert = Alert(
                    id=str(uuid.uuid4()),
                    rule_id=rule.id,
                    feature_name=feat,
                    detector_type=detector,
                    score=score,
                    threshold=0.20,
                    severity="critical",
                    model_version=settings.MODEL_VERSION,
                    window_id=event.window_id,
                    fired_at=timestamp,
                    resolved_at=timestamp + timedelta(hours=1) if random.random() > 0.5 else None,
                    suppressed=False
                )
                alerts_to_add.append(alert)

        session.add_all(events_to_add)
        session.add_all(alerts_to_add)
        await session.commit()
        
    print(f"Successfully inserted {len(events_to_add)} drift events and {len(alerts_to_add)} alerts!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
