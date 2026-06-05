# Real-Time ML Model Drift Detection System

## 1. Description
A comprehensive, containerized system for intercepting ML inference requests, detecting statistical distribution drift in real-time, firing deduplicated alerts, and automatically triggering Airflow retraining pipelines.

## 2. Architecture Diagram
```
[Client] -> [Interceptor API] -> [Kafka: inference.features]
                    |
              [Circuit Breaker (Redis)]

[Kafka: inference.features] -> [Faust Stream Processor (RocksDB Windows)] -> [Kafka: drift.scores]

[Kafka: drift.scores] -> [Alerter (Redis Dedup)] -> [Kafka: drift.alerts] / [Slack/PD]
                             |
                      [Airflow DAGs] -> Retraining Pipeline

[Dashboard (FastAPI)] <--- WebSockets (from Kafka scores/alerts)
```

## 3. Tech Stack
- **Python 3.11**
- **FastAPI**: API & Dashboard Backend
- **Faust-Streaming**: Real-time tumbling windows & stream processing
- **Apache Kafka**: Distributed event bus
- **PostgreSQL**: Async storage for baselines, events, rules
- **Redis**: Shared state, deduplication, circuit breakers, rate limiting
- **Airflow**: Retraining pipelines (KubernetesExecutor)
- **MLflow**: Model registry & tracking
- **Prometheus/Grafana**: Observability
- **Vanilla JS / Chart.js**: Frontend

## 4. Setup Instructions
1. Install Docker & Docker Compose.
2. Clone repository.
3. Configure `.env` from `.env.example`.
4. Run `make build` and `make up`.

## 5. Usage
1. Open `http://localhost:8080` for Airflow.
2. Open `http://localhost:5000` for MLflow.
3. Open `http://localhost:3000` for Grafana.
4. Open `https://localhost:443` for the Dashboard (use `make create-admin` first).

## 6. Components
- **Interceptor**: High-throughput FastAPI proxy logging features to Kafka. Uses a Redis-backed circuit breaker.
- **Processor**: Faust agents tumbling windows (1k size / 60s) statefully with RocksDB. Computes KL Divergence, PSI, and MMD.
- **Alert Engine**: Evaluates scores against DB rules. Deduplicates via Redis `SET NX EX`.
- **Dashboard**: Live WebSocket updates via Kafka consumption. Vanilla JS.
- **Retraining**: Airflow DAG `drift_triggered_retrain` validates drift and trains a scikit-learn model, logging to MLflow.

## 7. Metrics & Observability
- `drift_interceptor_requests_total`
- `drift_interceptor_failures_total`
- `circuit_breaker_state`
- `drift_alerts_fired_total`
- Dashboards available in Grafana `Drift Dashboards` folder.

## 8. Features

### Automatic Baseline Registration
The Interceptor automatically detects unseen combinations of `model_version` and `feature_name`. It builds a distributed warmup buffer in Redis and, upon reaching a configurable threshold (`BASELINE_WARMUP_MIN_SAMPLES`), atomically registers the baseline to Postgres and invalidates the in-memory caches via Kafka.

### Distributed State (Redis Key Reference)
We strictly enforce a centralized definition for Redis keys to ensure distributed consistency and avoid magic strings:
| Key Pattern | Purpose |
|-------------|---------|
| `circuit_breaker:{service_name}:state` | Stores open/half_open/closed state |
| `circuit_breaker:{service_name}:failure_count` | Tracks continuous failures |
| `alert_dedup:{feature_name}:{detector_type}` | SET NX TTL lock for deduplication |
| `baseline_warmup:{model_version}:{feature_name}` | RPUSH list of live inference values |
| `baseline_reg_lock:{model_version}:{feature_name}` | SET NX EX lock to prevent race conditions |

### Real-Time Observability
- Prometheus metrics collected from 7 internal components via Docker bridge.
- Grafana provisioned with `drift.json` for 13 panels covering Ops, System, and ML drift scores.

## 8. Development
- `make test`: Run unit tests
- `make test-auto-baseline`: Run specific auto-baseline integration tests
- `make mypy`: Run type checking
- `make bandit`: Run security scan
- `make verify-grafana`: Verify Grafana dashboard provisioning

## 9. Security
- Non-root containers (uid: 1001).
- Circuit breaker fails open.
- Rate limiting (Redis/SlowAPI).
- JWT Authentication for WebSockets & APIs.
- Strict Content Security Policies (CSP).

## 10. Data Flow
1. `POST /api/v1/predict` (Interceptor)
2. Features published to `inference.features`
4. Reference Store loads baselines from Postgres.
5. Scores published to `drift.scores`.
6. Rules engine evaluates thresholds.
7. Alerts deduplicated (Redis) and published to `drift.alerts`.
8. Airflow DAG triggered (or simulates trigger) -> MLflow Model Version promoted.

## 11. Custom Scripts
- `scripts/load_baselines.py`: Synthesize and load base distributions.
- `scripts/simulate_drift.py`: Simulate production traffic with optional drift injection.
- `scripts/create_admin_user.py`: Bootstrap dashboard user.

## 12. Deployment

### Kubernetes (Production)
- Kubernetes manifests provided in `k8s/`.
- Includes HPA (scaling on Kafka lag), PDBs, and Network Policies.
- Configuration via ConfigMap and Secret.

### DigitalOcean (Managed App Platform)
1. Push your repository to GitHub/GitLab.
2. In DigitalOcean, create a new **App**.
3. Select your repository and let DigitalOcean auto-detect the Dockerfiles.
4. For services like `drift-interceptor` and `drift-processor`, configure them as **Workers** or **Web Services** depending on if they expose a port.
5. Add managed **PostgreSQL** and **Redis** clusters through the DigitalOcean interface.
6. Provide the `DATABASE_URL` and `REDIS_URL` connection strings in the App-level environment variables.
7. Use Confluent Cloud or Aiven for the managed Kafka cluster, and supply the `KAFKA_BOOTSTRAP_SERVERS` credentials.

### Render (PaaS)
1. Create a new `render.yaml` Blueprint in the root of your repository to define your services.
2. Define a **PostgreSQL** database and a **Redis** instance in the Blueprint.
3. Define **Web Services** for `drift-interceptor` and `drift-dashboard`.
4. Define **Background Workers** for `drift-processor` and `drift-alerter`.
5. Provide a managed Kafka cluster URI (e.g., Upstash or Confluent Cloud) via Environment Variables, as Render does not natively provide managed Kafka.
6. Connect your repository to Render, and it will automatically provision and deploy the stack.

## 13. API Endpoints
- `POST /api/v1/predict`
- `GET /api/v1/health`
- `POST /auth/token`
- `GET /api/v1/drift/scores`
- `GET /api/v1/drift/alerts`
- `WS /ws/live`

## 14. Extending
Add new detectors to `detectors/`. Implement the `BaseDetector` interface. Add the call in `processor/score_emitter.py`.

## 15. Known Issues / Limitations
- MMD is computationally heavy (O(n²)); keep `n_permutations` reasonable.
- Faust relies on specific RocksDB dependencies; ensure `rocksdict` is correctly compiled in the Docker container.

## 16. Support
Contact RAY.

## 17. License
MIT
