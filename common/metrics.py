from prometheus_client import Counter, Gauge, Histogram

# Drift Detector Metrics
drift_detector_kl_score = Gauge(
    "drift_detector_kl_score", 
    "KL divergence score", 
    ["feature_name", "model_version"]
)
drift_detector_psi_score = Gauge(
    "drift_detector_psi_score", 
    "PSI score", 
    ["feature_name", "model_version"]
)
drift_detector_mmd_pvalue = Gauge(
    "drift_detector_mmd_pvalue", 
    "MMD p-value", 
    ["model_version"]
)

# Alerts
drift_alerts_fired_total = Counter(
    "drift_alerts_fired_total", 
    "Total number of drift alerts fired", 
    ["feature_name", "detector_type", "severity"]
)
drift_alerts_suppressed_total = Counter(
    "drift_alerts_suppressed_total", 
    "Total number of drift alerts suppressed by deduplication", 
    ["feature_name", "detector_type"]
)

# Retraining
drift_retrains_triggered_total = Counter(
    "drift_retrains_triggered_total", 
    "Total retrains triggered", 
    ["trigger_reason"]
)

# Kafka
kafka_consumer_lag = Gauge(
    "kafka_consumer_lag", 
    "Kafka consumer lag", 
    ["consumer_group", "topic", "partition"]
)
inference_features_published_total = Counter(
    "inference_features_published_total", 
    "Total inference features published to Kafka"
)

# API & Dashboard
api_request_duration_seconds = Histogram(
    "api_request_duration_seconds", 
    "API request duration in seconds", 
    ["method", "endpoint", "status_code"]
)
active_websocket_connections = Gauge(
    "active_websocket_connections", 
    "Current active WebSocket connections"
)
drift_baselines_auto_registered_total = Counter(
    "drift_baselines_auto_registered_total", 
    "Total baselines auto-registered by interceptor",
    ["model_version", "feature_name"]
)
