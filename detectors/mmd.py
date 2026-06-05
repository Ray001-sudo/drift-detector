import numpy as np
from datetime import datetime
from typing import Dict, Any, List
from detectors.base import BaseDriftDetector
from common.metrics import drift_detector_mmd_pvalue
from common.config import settings
from scipy.spatial.distance import cdist # type: ignore

class MMDDetector(BaseDriftDetector):
    def __init__(self, threshold_p: float = 0.05, max_samples: int = 500, n_permutations: int = 200):
        self.threshold_p = threshold_p
        self.max_samples = max_samples
        self.n_permutations = n_permutations

    def detect(self, reference_matrix: np.ndarray, production_matrix: np.ndarray, feature_names: List[str]) -> Dict[str, Any]: # type: ignore
        # Subsample to max 500 rows for efficiency
        # Set fixed seed based on some criteria, or just fixed seed to be reproducible for the same window
        rng = np.random.RandomState(42)
        
        if reference_matrix.shape[0] > self.max_samples:
            idx = rng.choice(reference_matrix.shape[0], self.max_samples, replace=False)
            X = reference_matrix[idx]
        else:
            X = reference_matrix
            
        if production_matrix.shape[0] > self.max_samples:
            idx = rng.choice(production_matrix.shape[0], self.max_samples, replace=False)
            Y = production_matrix[idx]
        else:
            Y = production_matrix

        # Median heuristic for bandwidth sigma
        # Pairwise distances of a combined subset to find median
        subset_X = X[:min(X.shape[0], 200)]
        subset_Y = Y[:min(Y.shape[0], 200)]
        combined = np.vstack([subset_X, subset_Y])
        dists = cdist(combined, combined, metric='euclidean')
        median_dist = np.median(dists[dists > 0])
        
        if median_dist == 0.0:
            sigma = 1.0
        else:
            sigma = median_dist / np.sqrt(2)

        def rbf_kernel(A: np.ndarray, B: np.ndarray) -> np.ndarray:
            sq_dists = cdist(A, B, 'sqeuclidean')
            return np.exp(-sq_dists / (2 * sigma ** 2))

        # Unbiased MMD^2 estimator
        K_XX = rbf_kernel(X, X)
        K_YY = rbf_kernel(Y, Y)
        K_XY = rbf_kernel(X, Y)
        
        m = X.shape[0]
        n = Y.shape[0]

        # Remove diagonal for unbiased estimation
        np.fill_diagonal(K_XX, 0)
        np.fill_diagonal(K_YY, 0)

        term_XX = np.sum(K_XX) / (m * (m - 1)) if m > 1 else 0
        term_YY = np.sum(K_YY) / (n * (n - 1)) if n > 1 else 0
        term_XY = np.sum(K_XY) * 2 / (m * n)

        mmd_score = term_XX + term_YY - term_XY

        # Permutation test
        Z = np.vstack([X, Y])
        total_samples = m + n
        K_ZZ = rbf_kernel(Z, Z)
        np.fill_diagonal(K_ZZ, 0)

        mmd_null = np.zeros(self.n_permutations)
        for i in range(self.n_permutations):
            perm_idx = rng.permutation(total_samples)
            idx_X = perm_idx[:m]
            idx_Y = perm_idx[m:]
            
            K_XX_perm = K_ZZ[np.ix_(idx_X, idx_X)]
            K_YY_perm = K_ZZ[np.ix_(idx_Y, idx_Y)]
            K_XY_perm = K_ZZ[np.ix_(idx_X, idx_Y)]
            
            term_XX_perm = np.sum(K_XX_perm) / (m * (m - 1)) if m > 1 else 0
            term_YY_perm = np.sum(K_YY_perm) / (n * (n - 1)) if n > 1 else 0
            term_XY_perm = np.sum(K_XY_perm) * 2 / (m * n)
            
            mmd_null[i] = term_XX_perm + term_YY_perm - term_XY_perm

        p_value = np.mean(mmd_null >= mmd_score)
        is_drifted = p_value < self.threshold_p

        # Update prometheus metric
        drift_detector_mmd_pvalue.labels(model_version=settings.MODEL_VERSION).set(float(p_value))

        return {
            "mmd_score": float(mmd_score),
            "p_value": float(p_value),
            "is_drifted": bool(is_drifted),
            "feature_names": feature_names,
            "timestamp": datetime.utcnow()
        }
