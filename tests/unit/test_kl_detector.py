import pytest
import numpy as np
from detectors.kl_divergence import KLDivergenceDetector

def test_identical_distributions():
    detector = KLDivergenceDetector(threshold=0.15)
    np.random.seed(42)
    ref = np.random.normal(0, 1, 1000)
    prod = np.random.normal(0, 1, 1000)
    
    res = detector.detect(ref, prod, "test_feat")
    assert res["kl_score"] < 0.15
    assert not res["is_drifted"]

def test_shifted_distributions():
    detector = KLDivergenceDetector(threshold=0.15)
    np.random.seed(42)
    ref = np.random.normal(0, 1, 1000)
    prod = np.random.normal(2, 1, 1000)
    
    res = detector.detect(ref, prod, "test_feat")
    assert res["kl_score"] > 0.15
    assert res["is_drifted"]

def test_single_value_distributions():
    detector = KLDivergenceDetector(threshold=0.15)
    ref = np.array([5.0, 5.0, 5.0])
    prod = np.array([5.0, 5.0, 5.0])
    res = detector.detect(ref, prod, "test_feat")
    assert res["kl_score"] == 0.0
    
    prod_shifted = np.array([6.0, 6.0, 6.0])
    res_shifted = detector.detect(ref, prod_shifted, "test_feat")
    assert res_shifted["is_drifted"]
