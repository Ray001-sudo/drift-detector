import pytest
import numpy as np
from detectors.psi import PSIDetector

def test_stable_psi():
    detector = PSIDetector(n_bins=10, threshold=0.2)
    np.random.seed(42)
    ref = np.random.normal(0, 1, 1000)
    prod = np.random.normal(0, 1, 1000)
    
    res = detector.detect(ref, prod, "test_feat")
    assert res["psi_score"] < 0.1
    assert not res["is_drifted"]

def test_drifted_psi():
    detector = PSIDetector(n_bins=10, threshold=0.2)
    np.random.seed(42)
    ref = np.random.normal(0, 1, 1000)
    prod = np.random.normal(2, 1, 1000)
    
    res = detector.detect(ref, prod, "test_feat")
    assert res["psi_score"] > 0.2
    assert res["is_drifted"]

def test_categorical_psi():
    detector = PSIDetector(n_bins=10, threshold=0.2)
    ref = np.array([1, 1, 1, 2, 2, 3])
    prod = np.array([1, 2, 2, 2, 3, 3])
    
    res = detector.detect(ref, prod, "test_feat")
    assert res["psi_score"] > 0
    assert len(res["bin_breakdown"]) >= 3
