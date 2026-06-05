import os
import mlflow # type: ignore
from mlflow.tracking import MlflowClient # type: ignore

def promote_model(validation_result: dict) -> dict:
    if not validation_result.get("is_promoted"):
        return {"status": "skipped"}
        
    run_id = validation_result["run_id"]
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
    client = MlflowClient()
    
    model_name = "drift_model"
    
    try:
        client.create_registered_model(model_name)
    except Exception:
        pass
        
    model_version = client.create_model_version(
        name=model_name,
        source=f"runs:/{run_id}/model",
        run_id=run_id
    )
    
    # Transition to Production
    client.transition_model_version_stage(
        name=model_name,
        version=model_version.version,
        stage="Production",
        archive_existing_versions=True
    )
    
    # Tag run
    client.set_tag(run_id, "triggered_by", "drift")
    
    return {
        "status": "promoted",
        "new_version": model_version.version,
        "old_f1": validation_result["old_f1"],
        "new_f1": validation_result["new_f1"],
        "run_id": run_id
    }
