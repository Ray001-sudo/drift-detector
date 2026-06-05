import os
import mlflow # type: ignore
from mlflow.tracking import MlflowClient # type: ignore

def validate_model(train_result: dict) -> dict:
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
    client = MlflowClient()
    
    new_f1 = train_result["f1_score"]
    
    try:
        # Fetch current production model F1
        # (Assuming model is named 'drift_model' in registry)
        prod_versions = client.get_latest_versions("drift_model", stages=["Production"])
        if prod_versions:
            prod_run_id = prod_versions[0].run_id
            prod_run = client.get_run(prod_run_id)
            prod_f1 = prod_run.data.metrics.get("f1_score", 0.0)
        else:
            prod_f1 = 0.0
    except Exception:
        prod_f1 = 0.0
        
    # Fail if new model is more than 2% worse
    if new_f1 < prod_f1 * 0.98:
        raise ValueError(f"New model F1 ({new_f1:.4f}) is worse than production ({prod_f1:.4f}) by > 2%")
        
    return {
        "run_id": train_result["run_id"],
        "new_f1": new_f1,
        "old_f1": prod_f1,
        "is_promoted": True
    }
