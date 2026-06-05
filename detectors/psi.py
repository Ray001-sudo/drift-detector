import numpy as np
from datetime import datetime
from typing import Dict, Any, List
from detectors.base import BaseDriftDetector
from common.metrics import drift_detector_psi_score
from common.config import settings

class PSIDetector(BaseDriftDetector):
    def __init__(self, n_bins: int = 10, threshold: float = 0.2):
        self.n_bins = n_bins
        self.threshold = threshold
        self.epsilon = 1e-4

    def detect(self, reference_data: np.ndarray, production_data: np.ndarray, feature_name: str) -> Dict[str, Any]:
        # Handle categorical / ordinal data (few unique values)
        unique_refs = np.unique(reference_data)
        if len(unique_refs) <= self.n_bins:
            # Categorical handling
            bins = np.append(unique_refs, [np.max(unique_refs) + 1])
        else:
            # Percentile-based edges (equal-frequency binning)
            percentiles = np.linspace(0, 100, self.n_bins + 1)
            bins = np.percentile(reference_data, percentiles)
            # Ensure bins are unique to avoid np.digitize issues
            bins = np.unique(bins)
            if len(bins) < 2:
                bins = np.array([np.min(reference_data), np.max(reference_data) + 1])

        min_edge = bins[0]
        max_edge = bins[-1]
        
        # Clip production data to [min_edge, max_edge]
        clipped_production = np.clip(production_data, min_edge, max_edge)

        # Calculate histograms
        ref_counts, _ = np.histogram(reference_data, bins=bins)
        prod_counts, _ = np.histogram(clipped_production, bins=bins)

        # Convert to percentages
        ref_pct = ref_counts / np.sum(ref_counts)
        prod_pct = prod_counts / np.sum(prod_counts)

        # Apply epsilon smoothing
        ref_pct = np.where(ref_pct == 0, self.epsilon, ref_pct)
        prod_pct = np.where(prod_pct == 0, self.epsilon, prod_pct)

        # PSI calculation
        psi_values = (prod_pct - ref_pct) * np.log(prod_pct / ref_pct)
        psi_score = float(np.sum(psi_values))

        is_drifted = psi_score > self.threshold

        bin_breakdown = []
        for i in range(len(bins) - 1):
            bin_breakdown.append({
                "bin_range": (float(bins[i]), float(bins[i+1])),
                "reference_pct": float(ref_pct[i]),
                "production_pct": float(prod_pct[i]),
                "contribution": float(psi_values[i])
            })

        # Update prometheus metric
        drift_detector_psi_score.labels(feature_name=feature_name, model_version=settings.MODEL_VERSION).set(psi_score)

        return {
            "psi_score": psi_score,
            "is_drifted": is_drifted,
            "bin_breakdown": bin_breakdown,
            "feature_name": feature_name,
            "timestamp": datetime.utcnow()
        }
