import asyncio
import httpx
import numpy as np
import uuid
import time

INTERCEPTOR_URL = "http://localhost:8000/api/v1/inference"  # Assumed interceptor endpoint
CONCURRENCY = 50

async def send_requests(client: httpx.AsyncClient, data: list[dict], batch_name: str) -> None:
    sem = asyncio.Semaphore(CONCURRENCY)
    
    async def _send(payload: dict, idx: int) -> None:
        async with sem:
            try:
                resp = await client.post(INTERCEPTOR_URL, json=payload)
                if (idx + 1) % 100 == 0:
                    print(f"[{batch_name}] Sent {idx + 1} requests... (Last status: {resp.status_code})")
            except Exception as e:
                print(f"Error sending request: {e}")

    tasks = [_send(payload, i) for i, payload in enumerate(data)]
    await asyncio.gather(*tasks)

async def main() -> None:
    print("=== Simulating Drift ===")
    
    # 1. Generate normal traffic (1000 requests) matching baselines
    normal_data = []
    for _ in range(1000):
        normal_data.append({
            "request_id": str(uuid.uuid4()),
            "features": {
                "age": float(np.clip(np.random.normal(38, 12), 18, 85)),
                "income": float(np.clip(np.random.lognormal(10.8, 0.5), 15000, 500000)),
                "credit_score": float(np.clip(np.random.normal(680, 80), 300, 850)),
                "tenure": float(np.clip(np.random.exponential(3), 0, 30))
            }
        })
        
    # 2. Generate drifted traffic (1000 requests) - mean shifted by 2 std devs
    drifted_data = []
    for _ in range(1000):
        drifted_data.append({
            "request_id": str(uuid.uuid4()),
            "features": {
                "age": float(np.clip(np.random.normal(62, 12), 18, 85)), # Drifted
                "income": float(np.clip(np.random.lognormal(10.8, 0.5), 15000, 500000)),
                "credit_score": float(np.clip(np.random.normal(520, 80), 300, 850)), # Drifted
                "tenure": float(np.clip(np.random.exponential(3), 0, 30))
            }
        })

    async with httpx.AsyncClient(timeout=10.0) as client:
        print("Sending 1,000 normal baseline requests...")
        await send_requests(client, normal_data, "Normal")
        
        print("\nWaiting 10 seconds to allow processor window to close...")
        time.sleep(10)
        
        print("\nSending 1,000 drifted requests...")
        await send_requests(client, drifted_data, "Drifted")

    print("\nDrift simulation complete. Check the dashboard!")

if __name__ == "__main__":
    asyncio.run(main())
