from datetime import datetime
import numpy as np
import logging
from processor.main import app
from processor.score_emitter import emit_drift_scores
from reference_store.store import store as ref_store

logger = logging.getLogger(__name__)

# Topic definition
features_topic = app.topic('inference.features', value_type=dict)
baseline_registered_topic = app.topic('baseline.registered', value_type=dict)

# RocksDB backed tumbling window
# 1000 records or 60 seconds
from datetime import timedelta
from typing import List, Dict

# In Faust, windowing is usually done via Table.
# However, combining a size trigger (1000) AND time trigger (60s) exactly is complex in pure Faust tables.
# We will manually aggregate in a local state / table and flush based on count or time.
# To keep RocksDB checkpointing, we use a Faust Table.

window_state = app.Table(
    'feature_windows',
    default=lambda: {"count": 0, "samples": {}, "start_time": datetime.utcnow().timestamp()},
    partitions=3
)

@app.task
async def initialize_reference_store() -> None:
    await ref_store.initialize()

@app.timer(interval=10.0)
async def check_time_windows() -> None:
    # Faust timers run on all worker instances. We can iterate over local partition keys.
    # Flush windows older than 60s.
    now = datetime.utcnow().timestamp()
    keys_to_flush = []
    
    for key, data in window_state.items():
        if data["count"] > 0 and (now - data["start_time"]) >= 60.0:
            keys_to_flush.append(key)
            
    for key in keys_to_flush:
        data = window_state[key]
        if data["count"] > 0: # Double check
            await process_window(key, data)
            window_state[key] = {"count": 0, "samples": {}, "start_time": datetime.utcnow().timestamp()}

async def process_window(key: str, data: dict) -> None:
    # Model version is used as the key
    model_version = key
    count = data["count"]
    samples = data["samples"]
    window_start = datetime.fromtimestamp(data["start_time"])
    window_end = datetime.utcnow()
    
    logger.info(f"Processing window for {model_version} with {count} samples")
    
    await emit_drift_scores(
        model_version=model_version,
        samples=samples,
        count=count,
        window_start=window_start,
        window_end=window_end
    )

@app.agent(features_topic)
async def process_features(stream: faust.Stream) -> None: # type: ignore
    async for event in stream:
        mv = event.get("model_version", "unknown")
        features = event.get("features", {})
        
        data = window_state[mv]
        
        # Append features
        for k, v in features.items():
            if k not in data["samples"]:
                data["samples"][k] = []
            try:
                # Handle schema evolution gracefully
                data["samples"][k].append(float(v))
            except (ValueError, TypeError):
                # Ignore unknown/uncastable fields gracefully
                pass
                
        data["count"] += 1
        
        # Check size trigger
        if data["count"] >= 1000:
            await process_window(mv, data)
            # Reset window
            window_state[mv] = {"count": 0, "samples": {}, "start_time": datetime.utcnow().timestamp()}
        else:
            window_state[mv] = data

@app.agent(baseline_registered_topic)
async def process_baseline_registration(stream: faust.Stream) -> None: # type: ignore
    async for event in stream:
        mv = event.get("model_version")
        fn = event.get("feature_name")
        if mv and fn:
            await ref_store.refresh_baseline(fn, mv)
