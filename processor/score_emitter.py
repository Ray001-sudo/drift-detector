import uuid
import logging
import numpy as np
from datetime import datetime
from typing import Dict, List, Any
from processor.main import app
from processor.reference_store.store import store as ref_store
from detectors.kl_divergence import KLDivergenceDetector
from detectors.psi import PSIDetector
from detectors.mmd import MMDDetector
from common.schemas import DriftScoreEventSchema

logger = logging.getLogger(__name__)

scores_topic = app.topic('drift.scores', value_type=dict)

kl_detector = KLDivergenceDetector()
psi_detector = PSIDetector()
mmd_detector = MMDDetector()

async def emit_drift_scores(
    model_version: str, 
    samples: Dict[str, List[float]], 
    count: int, 
    window_start: datetime, 
    window_end: datetime
) -> None:
    
    window_id = str(uuid.uuid4())
    events = []
    
    # 1. Single Feature Detectors (KL, PSI)
    feature_names = list(samples.keys())
    for feature_name in feature_names:
        prod_data = np.array(samples[feature_name])
        ref_data = ref_store.get_baseline(feature_name, model_version)
        
        if ref_data is None:
            logger.debug(f"No reference data for {feature_name} (model {model_version}). Skipping.")
            continue
            
        # KL
        try:
            kl_res = kl_detector.detect(ref_data, prod_data, feature_name)
            events.append(DriftScoreEventSchema(
                window_id=window_id,
                feature_name=feature_name,
                detector_type="kl",
                score=kl_res["kl_score"],
                is_drifted=kl_res["is_drifted"],
                model_version=model_version,
                window_start=window_start,
                window_end=window_end,
                sample_count=count
            ))
        except Exception as e:
            logger.error(f"KL detection failed for {feature_name}: {e}")
            
        # PSI
        try:
            psi_res = psi_detector.detect(ref_data, prod_data, feature_name)
            events.append(DriftScoreEventSchema(
                window_id=window_id,
                feature_name=feature_name,
                detector_type="psi",
                score=psi_res["psi_score"],
                is_drifted=psi_res["is_drifted"],
                model_version=model_version,
                window_start=window_start,
                window_end=window_end,
                sample_count=count
            ))
        except Exception as e:
            logger.error(f"PSI detection failed for {feature_name}: {e}")

    # 2. Multivariate Detector (MMD)
    # Build matrices for features that have baselines
    valid_features = [f for f in feature_names if ref_store.get_baseline(f, model_version) is not None]
    
    if valid_features and len(valid_features) > 0:
        # We need corresponding lengths. Since reference arrays might differ in length, MMD handles unequal rows.
        # But for MMD, each row is a sample across all features.
        # So we need to construct a 2D array of reference samples and 2D array of prod samples.
        # Assuming reference data for all features in a given baseline were captured together.
        # Find minimum length to truncate or just take a valid subset.
        # Usually MMD requires the same number of columns.
        min_ref_len = min([len(ref_store.get_baseline(f, model_version)) for f in valid_features]) # type: ignore
        min_prod_len = min([len(samples[f]) for f in valid_features])
        
        if min_ref_len > 0 and min_prod_len > 0:
            try:
                ref_matrix = np.column_stack([ref_store.get_baseline(f, model_version)[:min_ref_len] for f in valid_features]) # type: ignore
                prod_matrix = np.column_stack([samples[f][:min_prod_len] for f in valid_features])
                
                mmd_res = mmd_detector.detect(ref_matrix, prod_matrix, valid_features)
                
                events.append(DriftScoreEventSchema(
                    window_id=window_id,
                    feature_name="multivariate",
                    detector_type="mmd",
                    score=mmd_res["mmd_score"], # we can store mmd_score or p_value in the score field
                    is_drifted=mmd_res["is_drifted"],
                    model_version=model_version,
                    window_start=window_start,
                    window_end=window_end,
                    sample_count=count,
                    metadata={"p_value": mmd_res["p_value"], "features": valid_features}
                ))
            except Exception as e:
                logger.error(f"MMD detection failed: {e}")

    # Publish all events to drift.scores topic
    for event in events:
        await scores_topic.send(value=event.model_dump())
