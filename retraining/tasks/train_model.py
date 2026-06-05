import pandas as pd
import mlflow # type: ignore
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
import matplotlib.pyplot as plt
import seaborn as sns
import os

def train_model(data_path: str) -> dict:
    df = pd.read_csv(data_path)
    X = df.drop(columns=["default"])
    y = df["default"]
    
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
    mlflow.set_experiment("drift_retraining")
    
    with mlflow.start_run() as run:
        pipeline = Pipeline([
            ('scaler', StandardScaler()),
            ('classifier', LogisticRegression(max_iter=1000))
        ])
        
        pipeline.fit(X, y)
        y_pred = pipeline.predict(X)
        
        # Log params
        mlflow.log_param("model_type", "LogisticRegression")
        mlflow.log_param("scaler", "StandardScaler")
        
        # Classification report
        report = classification_report(y, y_pred, output_dict=True)
        f1_score = report['weighted avg']['f1-score']
        mlflow.log_metric("f1_score", f1_score)
        
        # Log model
        mlflow.sklearn.log_model(pipeline, "model")
        
        # Confusion matrix artifact
        cm = confusion_matrix(y, y_pred)
        plt.figure(figsize=(6,5))
        sns.heatmap(cm, annot=True, fmt='d')
        plt.title('Confusion Matrix')
        plt.ylabel('Actual')
        plt.xlabel('Predicted')
        cm_path = "/tmp/confusion_matrix.png"
        plt.savefig(cm_path)
        mlflow.log_artifact(cm_path)
        
        return {
            "run_id": run.info.run_id,
            "f1_score": f1_score
        }
