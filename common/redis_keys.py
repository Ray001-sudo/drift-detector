# Centralized definition of all Redis key patterns

CIRCUIT_BREAKER_STATE = "circuit_breaker:{service_name}:state"
CIRCUIT_BREAKER_FAILURES = "circuit_breaker:{service_name}:failure_count"
ALERT_DEDUP = "alert_dedup:{feature_name}:{detector_type}"
BASELINE_WARMUP = "baseline_warmup:{model_version}:{feature_name}"
BASELINE_REG_LOCK = "baseline_reg_lock:{model_version}:{feature_name}"
