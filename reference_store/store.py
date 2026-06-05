import numpy as np
from sqlalchemy import select
from typing import Dict, Optional, List
from common.database import async_session_maker
from common.models import FeatureBaseline
import logging

logger = logging.getLogger(__name__)

class ReferenceStore:
    def __init__(self):
        # In-memory cache loaded on startup
        self._baselines: Dict[str, Dict[str, np.ndarray]] = {}
        # Format: {model_version: {feature_name: numpy_array}}

    async def initialize(self) -> None:
        """Load all baselines from DB into memory."""
        logger.info("Initializing reference store from database")
        async with async_session_maker() as session:
            stmt = select(FeatureBaseline)
            result = await session.execute(stmt)
            baselines = result.scalars().all()
            
            for b in baselines:
                mv = b.model_version
                if mv not in self._baselines:
                    self._baselines[mv] = {}
                self._baselines[mv][b.feature_name] = np.array(b.raw_samples, dtype=np.float64)
                
            logger.info(f"Loaded {len(baselines)} feature baselines into memory.")

    def get_baseline(self, feature_name: str, model_version: str) -> Optional[np.ndarray]:
        return self._baselines.get(model_version, {}).get(feature_name)

    def get_all_baselines(self, model_version: str) -> Dict[str, np.ndarray]:
        return self._baselines.get(model_version, {})

    async def refresh_baseline(self, feature_name: str, model_version: str) -> None:
        """Fetch a single baseline from DB and update cache."""
        async with async_session_maker() as session:
            stmt = select(FeatureBaseline).where(
                FeatureBaseline.feature_name == feature_name,
                FeatureBaseline.model_version == model_version
            )
            b = (await session.execute(stmt)).scalar_one_or_none()
            if b:
                if model_version not in self._baselines:
                    self._baselines[model_version] = {}
                self._baselines[model_version][feature_name] = np.array(b.raw_samples, dtype=np.float64)
                logger.info(f"Refreshed baseline for {feature_name} {model_version}")

    async def update_baseline(self, feature_name: str, model_version: str, new_samples: np.ndarray, user_id: str) -> None:
        """Update the baseline in DB atomically and refresh cache."""
        async with async_session_maker() as session:
            stmt = select(FeatureBaseline).where(
                FeatureBaseline.feature_name == feature_name,
                FeatureBaseline.model_version == model_version
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            
            from datetime import datetime
            if existing:
                existing.raw_samples = new_samples.tolist()
                existing.sample_count = len(new_samples)
                existing.computed_at = datetime.utcnow()
                existing.created_by = user_id
            else:
                new_baseline = FeatureBaseline(
                    feature_name=feature_name,
                    model_version=model_version,
                    raw_samples=new_samples.tolist(),
                    sample_count=len(new_samples),
                    computed_at=datetime.utcnow(),
                    created_by=user_id
                )
                session.add(new_baseline)
            
            await session.commit()
            
            # Update cache
            if model_version not in self._baselines:
                self._baselines[model_version] = {}
            self._baselines[model_version][feature_name] = new_samples

store = ReferenceStore()
