import asyncio
import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime
from sqlalchemy import select
from common.database import async_session_maker
from common.models import FeatureBaseline
from common.config import settings

async def main() -> None:
    baselines_dir = "data/baselines/"
    if len(sys.argv) > 1:
        if sys.argv[1].startswith("--baselines-dir="):
            baselines_dir = sys.argv[1].split("=")[1]
    
    if not os.path.isdir(baselines_dir):
        print(f"Directory not found: {baselines_dir}")
        sys.exit(1)

    model_version = settings.MODEL_VERSION
    results = []

    async with async_session_maker() as session:
        for filename in os.listdir(baselines_dir):
            if not filename.endswith(".csv"):
                continue
            
            feature_name = filename[:-4]
            filepath = os.path.join(baselines_dir, filename)
            
            try:
                # Validate format strictly
                df = pd.read_csv(filepath, header=None)
                if df.shape[1] > 1:
                    print(f"Skipping {filename}: Multiple columns detected.")
                    results.append((feature_name, 0, "failed (multiple columns)"))
                    continue
                
                # Check if header exists by seeing if first value is numeric
                try:
                    float(df.iloc[0, 0])
                except ValueError:
                    print(f"Skipping {filename}: Header detected (first value not numeric).")
                    results.append((feature_name, 0, "failed (header detected)"))
                    continue

                if len(df) < 100:
                    print(f"Skipping {filename}: Fewer than 100 rows.")
                    results.append((feature_name, len(df), "failed (<100 rows)"))
                    continue
                
                if len(df) > 50000:
                    ans = input(f"File {filename} has >50,000 rows. Truncate to 50k? [y/N]: ")
                    if ans.lower() != 'y':
                        print(f"Skipping {filename}: Too large.")
                        results.append((feature_name, len(df), "skipped"))
                        continue
                    df = df.head(50000)

                arr = df[0].values
                
                if np.isnan(arr).any():
                    idx = np.where(np.isnan(arr))[0][0]
                    print(f"Error in {filename}: NaN value at row {idx}")
                    results.append((feature_name, len(arr), "failed (NaN)"))
                    continue
                
                if np.isinf(arr).any():
                    idx = np.where(np.isinf(arr))[0][0]
                    print(f"Error in {filename}: Infinite value at row {idx}")
                    results.append((feature_name, len(arr), "failed (Inf)"))
                    continue

                # Basic Stats
                print(f"--- {feature_name} Stats ---")
                print(f"Min: {np.min(arr):.4f}, Max: {np.max(arr):.4f}, Mean: {np.mean(arr):.4f}, Std: {np.std(arr):.4f}")
                print(f"P25: {np.percentile(arr, 25):.4f}, P50: {np.percentile(arr, 50):.4f}, P75: {np.percentile(arr, 75):.4f}")
                
                # DB Check
                stmt = select(FeatureBaseline).where(
                    FeatureBaseline.feature_name == feature_name,
                    FeatureBaseline.model_version == model_version
                )
                existing = (await session.execute(stmt)).scalar_one_or_none()
                
                status = "inserted"
                if existing:
                    ans = input(f"Baseline for '{feature_name}' already exists for model version '{model_version}'. Overwrite? [y/N]: ")
                    if ans.lower() != 'y':
                        results.append((feature_name, len(arr), "skipped"))
                        continue
                    status = "updated"
                    existing.raw_samples = arr.tolist()
                    existing.sample_count = len(arr)
                    existing.computed_at = datetime.utcnow()
                else:
                    new_baseline = FeatureBaseline(
                        feature_name=feature_name,
                        model_version=model_version,
                        raw_samples=arr.tolist(),
                        sample_count=len(arr),
                        computed_at=datetime.utcnow(),
                        created_by="scripts/load_baselines.py"
                    )
                    session.add(new_baseline)
                
                await session.commit()
                results.append((feature_name, len(arr), status))

            except Exception as e:
                print(f"Error processing {filename}: {str(e)}")
                results.append((feature_name, 0, f"failed ({str(e)})"))
                
    print("\n=== Summary ===")
    print(f"{'Feature Name':<20} | {'Count':<10} | {'Status'}")
    print("-" * 50)
    for feat, count, stat in results:
        print(f"{feat:<20} | {count:<10} | {stat}")

if __name__ == "__main__":
    asyncio.run(main())
