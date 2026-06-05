import pytest
import numpy as np
from detectors.mmd import MMDDetector

def test_same_distribution():
    detector = MMDDetector(threshold_p=0.05, n_permutations=50)
    np.random.seed(42)
    ref = np.random.normal(0, 1, (200, 5))
    prod = np.random.normal(0, 1, (200, 5))
    
    res = detector.detect(ref, prod, ["f1", "f2", "f3", "f4", "f5"])
    assert res["p_value"] > 0.05
    assert not res["is_drifted"]

def test_different_distribution():
    detector = MMDDetector(threshold_p=0.05, n_permutations=50)
    np.random.seed(42)
    ref = np.random.normal(0, 1, (200, 5))
    prod = np.random.normal(1, 1, (200, 5)) # Shifted
    
    res = detector.detect(ref, prod, ["f1", "f2", "f3", "f4", "f5"])
    assert res["p_value"] < 0.05
    assert res["is_drifted"]
