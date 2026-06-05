import pandas as pd
import numpy as np

def fetch_training_data(validation_result: dict) -> str:
    print(f"Fetching training data. Validation info: {validation_result}")
    # Simulating data warehouse fetch of last 90 days.
    # Fetches in batches of 10,000 rows. Validates schema.
    
    # Generate synthetic training data
    np.random.seed(42)
    n_samples = 10000
    df = pd.DataFrame({
        "age": np.clip(np.random.normal(38, 12, n_samples), 18, 85),
        "income": np.clip(np.random.lognormal(10.8, 0.5, n_samples), 15000, 500000),
        "credit_score": np.clip(np.random.normal(680, 80, n_samples), 300, 850),
        "tenure": np.clip(np.random.exponential(3, n_samples), 0, 30),
        # Target variable
        "default": np.random.binomial(1, 0.15, n_samples)
    })
    
    path = "/tmp/training_data.csv"
    df.to_csv(path, index=False)
    print(f"Data saved to {path}")
    return path
