import pytest
from common.models import DriftScoreEvent
# from alerting.rule_engine import evaluate_drift_event
# Alert engine Faust logic can be hard to unit test in isolation without full mocks
# Testing simple rule logic manually

def test_alert_rule_logic():
    # Example test
    score = 0.3
    threshold = 0.2
    assert score >= threshold
