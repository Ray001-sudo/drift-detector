import numpy as np
from scipy.stats import gaussian_kde # type: ignore
from datetime import datetime
from typing import Dict, Any, Tuple
from detectors.base import BaseDriftDetector
from common.metrics import drift_detector_kl_score
from common.config import settings

class KLDivergenceDetector(BaseDriftDetector):
    def __init__(self, threshold: float = 0.15):
        self.threshold = threshold
        self.epsilon = 1e-10

    def detect(self, reference_samples: np.ndarray, production_samples: np.ndarray, feature_name: str) -> Dict[str, Any]:
        # Handle edge cases
        if len(np.unique(reference_samples)) == 1 or len(np.unique(production_samples)) == 1:
            # Single value distributions, KDE fails. We manually compute
            # simple shift check.
            if np.array_equal(np.unique(reference_samples), np.unique(production_samples)):
                score = 0.0
            else:
                score = 1.0 # arbitrary high value for total mismatch
            
            is_drifted = score > self.threshold
            return {
                "kl_score": score,
                "is_drifted": is_drifted,
                "confidence_interval": (0.0, 0.0),
                "feature_name": feature_name,
                "timestamp": datetime.utcnow()
            }

        kde_ref = gaussian_kde(reference_samples, bw_method='scott')
        kde_prod = gaussian_kde(production_samples, bw_method='scott')

        # Shared linspace grid
        min_val = min(np.min(reference_samples), np.min(production_samples))
        max_val = max(np.max(reference_samples), np.max(production_samples))
        
        # Extend slightly to capture tails
        grid_margin = (max_val - min_val) * 0.1
        grid = np.linspace(min_val - grid_margin, max_val + grid_margin, 500)

        p = kde_ref(grid)
        q = kde_prod(grid)

        # Laplace smoothing
        p = p + self.epsilon
        q = q + self.epsilon

        # Normalize so they integrate to 1
        p = p / np.sum(p)
        q = q / np.sum(q)

        # KL Divergence: sum(P * log(P/Q))
        # Wait: The reference is P, the production is Q. 
        # Typically we measure D_KL(P || Q) or D_KL(Q || P). 
        # Measuring how much production shifted FROM reference means D_KL(Production || Reference) -> sum(Q * log(Q/P))
        kl_score = float(np.sum(q * np.log(q / p)))
        is_drifted = kl_score > self.threshold

        # Update prometheus metric
        drift_detector_kl_score.labels(feature_name=feature_name, model_version=settings.MODEL_VERSION).set(kl_score)

        return {
            "kl_score": kl_score,
            "is_drifted": is_drifted,
            "confidence_interval": (kl_score * 0.9, kl_score * 1.1), # Simulated CI
            "feature_name": feature_name,
            "timestamp": datetime.utcnow()
        }
