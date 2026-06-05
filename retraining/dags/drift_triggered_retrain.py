from datetime import datetime, timedelta
from airflow.decorators import dag, task # type: ignore
from retraining.tasks.validate_drift import validate_drift_event
from retraining.tasks.fetch_data import fetch_training_data
from retraining.tasks.train_model import train_model
from retraining.tasks.validate_model import validate_model
from retraining.tasks.promote_model import promote_model
from retraining.tasks.notify import notify_promotion

default_args = {
    'owner': 'mlops',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

k8s_executor_config = {
    "KubernetesExecutor": {
        "request_cpu": "1",
        "request_memory": "2Gi",
        "limit_cpu": "2",
        "limit_memory": "4Gi",
    }
}

@dag(
    dag_id='drift_triggered_retrain',
    default_args=default_args,
    description='Retrains model when drift is detected',
    schedule_interval=None,
    start_date=datetime(2023, 1, 1),
    catchup=False,
    tags=['mlops', 'retraining']
)
def drift_retrain_dag():
    
    @task(executor_config=k8s_executor_config)
    def validate_drift_task(**context) -> dict:
        return validate_drift_event(context)
        
    @task(executor_config=k8s_executor_config)
    def fetch_data_task(validation_result: dict) -> str:
        return fetch_training_data(validation_result)
        
    @task(executor_config=k8s_executor_config)
    def train_task(data_path: str) -> dict:
        return train_model(data_path)
        
    @task(executor_config=k8s_executor_config)
    def validate_model_task(train_result: dict) -> dict:
        return validate_model(train_result)
        
    @task(executor_config=k8s_executor_config)
    def promote_task(validation_result: dict) -> dict:
        return promote_model(validation_result)
        
    @task(executor_config=k8s_executor_config)
    def notify_task(promotion_result: dict) -> None:
        notify_promotion(promotion_result)

    # Define DAG flow
    validation_res = validate_drift_task()
    data_path = fetch_data_task(validation_res)
    train_res = train_task(data_path)
    model_val_res = validate_model_task(train_res)
    promo_res = promote_task(model_val_res)
    notify_task(promo_res)

dag_instance = drift_retrain_dag()
