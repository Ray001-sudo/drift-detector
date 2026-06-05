# Real-Time ML Model Drift Detection System

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED.svg)](docker-compose.yml)
[![Kubernetes](https://img.shields.io/badge/kubernetes-ready-326CE5.svg)](k8s/)

> **Live Demo:** [https://yourdomain.com](https://yourdomain.com) &nbsp;|&nbsp; **Grafana:** [https://yourdomain.com:3000](https://yourdomain.com:3000)

![Dashboard Screenshot](docs/screenshots/grafana-drift-event.png)
*Live dashboard showing a drift event propagating through the pipeline — PSI score on the `age` feature climbing through the 0.20 threshold, triggering automatic retraining.*

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [System Architecture](#2-system-architecture)
3. [How Drift Detection Works](#3-how-drift-detection-works)
4. [Tech Stack](#4-tech-stack)
5. [Prerequisites](#5-prerequisites)
6. [Local Development Setup](#6-local-development-setup)
7. [Environment Variables](#7-environment-variables)
8. [Automatic Baseline Registration](#8-automatic-baseline-registration)
9. [Production Deployment](#9-production-deployment)
10. [Secrets Management](#10-secrets-management)
11. [Adding a New Model](#11-adding-a-new-model)
12. [Alert Configuration](#12-alert-configuration)
13. [Dashboard Guide](#13-dashboard-guide)
14. [Grafana Dashboard](#14-grafana-dashboard)
15. [Redis Key Reference](#15-redis-key-reference)
16. [Runbook](#16-runbook)
17. [Security Hardening Checklist](#17-security-hardening-checklist)
18. [Performance Characteristics](#18-performance-characteristics)
19. [Testing](#19-testing)
20. [Contributing](#20-contributing)
21. [License](#21-license)

---

## 1. Problem Statement

### The silent failure mode that kills production ML

When a machine learning model is trained, it learns statistical patterns from a fixed historical dataset. The model is then deployed and begins making predictions on live traffic. The problem is that the real world does not stay static. User demographics shift. Market conditions change. New device categories emerge. Fraudsters adapt their tactics. Seasonal patterns distort distributions. Over days, weeks, or months, the data flowing into the model in production begins to look increasingly different from the data it was trained on.

This is **data drift**, and it is the primary cause of silent model degradation in production.

The word "silent" is what makes it dangerous. The model does not throw an exception. It does not return an error code. It continues serving predictions with full confidence — but those predictions are increasingly wrong. By the time degradation becomes visible in business metrics (rising fraud rates, declining conversion, worsening patient outcomes), the model may have been underperforming for weeks. In high-stakes domains such as credit scoring, medical diagnosis, or fraud detection, this silent failure mode carries direct financial and human cost.

### What existing monitoring misses

Standard application monitoring (uptime checks, latency alerts, error rate dashboards) is completely blind to data drift. A model can have 99.9% uptime, sub-10ms p99 latency, and zero HTTP errors while producing predictions that are systematically wrong for an entire demographic segment. Accuracy-based monitoring helps but requires ground truth labels, which in many systems arrive days or weeks after the prediction. By the time labelled outcomes are available, the damage is already done.

### What this system does

This system provides continuous, real-time statistical monitoring of the *input feature distributions* flowing into any ML model — without requiring ground truth labels. It compares what the model is seeing now against what it was trained on, using three complementary statistical tests (KL-divergence, PSI, and MMD), and takes automated action when drift is detected: alerting on-call engineers via Slack and PagerDuty, and triggering a fully automated retraining pipeline that fetches fresh data, retrains the model, validates it, and promotes it to production — all without human intervention.

The result is a self-healing ML system that detects distribution shift within minutes of it beginning and responds before it materially affects prediction quality.

---

## 2. System Architecture

### ASCII Architecture Diagram

```
                        INFERENCE TRAFFIC
                              │
                              ▼
              ┌───────────────────────────────┐
              │      drift-interceptor        │
              │   FastAPI middleware layer     │
              │  Captures feature vectors     │
              │  Circuit breaker (Redis)       │
              │  Auto baseline registration   │
              └───────────┬───────────────────┘
                          │ RPUSH feature vectors
                          ▼
              ┌───────────────────────────────┐
              │           KAFKA               │
              │  inference.features  (3 part) │
              │  drift.scores        (3 part) │
              │  drift.alerts        (1 part) │
              │  baseline.registered (1 part) │
              │  inference.features.dlq       │
              └─────────┬──────────┬──────────┘
                        │          │
              ┌─────────▼──┐  ┌────▼──────────────────────┐
              │   drift-   │  │       drift-alerter        │
              │  processor │  │  Consumes drift.scores     │
              │            │  │  Rule engine (Postgres)    │
              │ Faust app  │  │  Dedup (Redis SET NX EX)   │
              │ Tumbling   │  │  Slack + PagerDuty notify  │
              │ windows    │  │  Auto-resolve logic        │
              │ 1000/60s   │  └────────────┬───────────────┘
              │ RocksDB    │               │ drift.alerts
              │ checkpoint │               ▼
              │            │  ┌────────────────────────────┐
              │ KL/PSI/MMD │  │         AIRFLOW            │
              │ detectors  │  │  drift_triggered_retrain   │
              │            │  │  DAG (KubernetesExecutor)  │
              └─────┬──────┘  │  validate → fetch →        │
                    │         │  train → validate →         │
                    │ emits   │  promote → notify           │
                    │ drift   └────────────┬───────────────┘
                    │ scores              │ promotes model
                    ▼                     ▼
              ┌───────────────────────────────────────────┐
              │                 MLFLOW                    │
              │  Model registry (Production/Staging)      │
              │  Experiment tracking                      │
              │  Artifact storage                         │
              └───────────────────────────────────────────┘
                    │
                    │ WebSocket broadcast (2s interval)
                    ▼
              ┌───────────────────────────────┐
              │      drift-dashboard          │
              │  FastAPI REST + WebSocket     │
              │  JWT authentication           │
              │  Rate limiting (SlowAPI)      │
              │  Security headers middleware  │
              │  Vanilla JS + Chart.js UI     │
              └───────────────────────────────┘

SHARED INFRASTRUCTURE:

  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────┐
  │  PostgreSQL  │    │    Redis     │    │        Prometheus        │
  │  16-alpine   │    │  7-alpine    │    │  Scrapes all /metrics    │
  │              │    │              │    │  endpoints every 5s      │
  │  users       │    │  Circuit     │    └────────────┬─────────────┘
  │  baselines   │    │  breaker     │                 │
  │  drift events│    │  Alert dedup │                 ▼
  │  alerts      │    │  Warmup buf  │    ┌──────────────────────────┐
  │  alert rules │    │  Rate limits │    │         Grafana          │
  │  audit_log   │    │              │    │  13 panels, 6 rows       │
  │  auth log    │    └──────────────┘    │  5s refresh              │
  └──────────────┘                        └──────────────────────────┘
```

### Data Flow Summary

1. An inference request hits the **interceptor**. The middleware captures the input feature vector (age, income, credit_score, etc.) and publishes it asynchronously to the `inference.features` Kafka topic. The model prediction continues with less than 2ms added latency.

2. The **processor** consumes `inference.features` via Faust-Streaming. It accumulates features into tumbling windows of 1,000 records or 60 seconds. On each window close, it runs KL-divergence, PSI, and MMD detectors against the stored reference baselines and emits a `DriftScoreEvent` to `drift.scores`.

3. The **alerter** consumes `drift.scores`. For each event, it evaluates configured alert rules stored in PostgreSQL. If a threshold is breached and the alert is not deduplicated, it fires a Slack notification, optionally a PagerDuty incident, inserts an alert record, and publishes to `drift.alerts`.

4. If drift severity exceeds the retraining threshold, the alerter triggers the **Airflow DAG** `drift_triggered_retrain` via REST API. The DAG validates the drift event, fetches fresh training data, retrains the model, validates F1 score against the current production model, promotes the winner to MLflow production, and notifies the team.

5. The **dashboard** backend serves a FastAPI REST API and a WebSocket endpoint that broadcasts current drift scores, alert states, and pipeline status to all connected browsers every 2 seconds.

---

## 3. How Drift Detection Works

The system uses three statistical methods simultaneously. Each catches different types of drift. A model passing all three is genuinely stable; a model failing any one warrants investigation.

### KL-Divergence (Kullback-Leibler Divergence)

KL-divergence measures how much one probability distribution differs from a reference distribution. Intuitively: if you drew a sample from the production distribution, how "surprised" would the training distribution be?

**Formula:**

```
KL(P ∥ Q) = Σ P(x) · log( P(x) / Q(x) )
```

Where P is the training (reference) distribution and Q is the production distribution.

- KL = 0 means the distributions are identical — no drift.
- KL > 0 means drift exists. Higher values indicate greater divergence.
- KL is asymmetric: KL(P∥Q) ≠ KL(Q∥P). We always compute training-vs-production, not the reverse, because we care specifically about how surprising production traffic is relative to training.

**Implementation details:** The system builds kernel density estimates (KDE) using `scipy.stats.gaussian_kde` with Scott's bandwidth rule, evaluates both KDEs on a shared 500-point linspace grid, and applies Laplace smoothing (ε = 1e-10) before computing KL to prevent division-by-zero on empty grid buckets.

**Thresholds:** KL < 0.08 = stable, 0.08–0.15 = warning, > 0.15 = drift.

**Best for:** Continuous features (age, income, transaction amount) where the shape of the distribution matters.

### PSI (Population Stability Index)

PSI originated in credit risk modelling to detect whether a loan scoring model's applicant pool had changed. It is a symmetric variant of KL-divergence expressed as a single interpretable number with well-established industry thresholds.

**Formula:**

```
PSI = Σ (Actual% − Expected%) × ln(Actual% / Expected%)
```

Where Expected% is the reference (training) bin percentage and Actual% is the production bin percentage.

**Thresholds:** PSI < 0.10 = stable (no action), 0.10–0.20 = moderate shift (monitor), > 0.20 = major shift (investigate and likely retrain).

**Implementation details:** The system uses equal-frequency binning (percentile-based bin edges) with 10 bins by default, clips production data to [min_edge, max_edge] to handle out-of-range values, and applies epsilon smoothing (1e-4) to prevent log-zero errors.

**Best for:** Both continuous and categorical features. PSI is the most actionable metric — the 0.10/0.20 thresholds are understood industry-wide, making it easy to configure alerts that operations teams can act on without statistical expertise.

### MMD (Maximum Mean Discrepancy)

MMD is fundamentally different from KL and PSI. While those methods test each feature individually, MMD tests whether the *joint* multivariate distribution of all features combined has changed. This catches a critical class of drift that the other two methods miss entirely: changes in the *correlations between features* rather than changes in individual feature distributions.

**Example of what only MMD catches:** Suppose `age` and `income` individually look stable (PSI < 0.10 for each). But in training, age and income were positively correlated (older applicants tended to earn more). In production, this correlation has reversed (younger high-earners dominate). KL and PSI see each feature's marginal distribution and report "stable." MMD sees the joint distribution has fundamentally changed and fires.

**Formula (unbiased estimator):**

```
MMD²(P, Q) = E[k(x,x')] - 2E[k(x,y)] + E[k(y,y')]
```

Where k is the RBF kernel with bandwidth σ selected via the median heuristic: σ = median(pairwise distances) / √2.

The system computes a permutation test p-value with 200 permutations. A p-value below 0.05 indicates the two samples are unlikely to have come from the same distribution.

**Implementation details:** Both matrices are subsampled to a maximum of 500 rows each for computational efficiency. The random seed is fixed per window for reproducibility. Computational complexity is O(n²) on the subsampled matrix.

**Thresholds:** p-value < 0.10 = warning, < 0.05 = drift.

### Why All Three Together

| Method | Catches | Misses |
|--------|---------|--------|
| KL-divergence | Continuous feature shape changes | Categorical features, multivariate correlations |
| PSI | Both continuous and categorical individual feature shifts | Multivariate correlation changes |
| MMD | Joint distribution changes, correlation shifts | Fine-grained per-feature attribution |

Running all three provides defence in depth. No single detector has a blind spot that an attacker (or a subtle distribution shift) can slip through undetected.

---

## 4. Tech Stack

| Component | Technology | Version | Why this over alternatives |
|-----------|-----------|---------|--------------------------|
| API framework | FastAPI | 0.109 | Async-native, automatic OpenAPI docs, Pydantic v2 integration. Flask is sync-first and slower under load. |
| Stream processing | Faust-Streaming | 0.10+ | Python-native Kafka streaming with stateful windowing and RocksDB checkpointing. Preferred over Flink for Python-first teams. |
| Message broker | Apache Kafka | 7.5.0 (Confluent) | Durable, replayable, partitioned. RabbitMQ lacks long-term retention; Redis Streams lack the ecosystem. |
| Database | PostgreSQL | 16-alpine | ACID transactions for baseline updates. SQLite has no async driver; MySQL has weaker JSON support. |
| ORM | SQLAlchemy | 2.0 (async) | Industry standard, async support in 2.0, Alembic migration integration. |
| Cache / state | Redis | 7-alpine | Atomic operations (SET NX EX) for distributed locking and deduplication. Used for circuit breaker state, alert dedup, and warmup buffers. |
| Workflow orchestration | Apache Airflow | 2.8.0 | Production standard for ML pipelines. Prefect is simpler but has less ecosystem. |
| Model tracking | MLflow | 2.9.2 | Model registry, experiment tracking, artifact storage in one tool. Weights & Biases is excellent but paid at scale. |
| Statistical computing | NumPy + SciPy | latest stable | KDE, KL-divergence, and MMD implemented directly — no drift library abstractions hiding the math. |
| Metrics | Prometheus + Grafana | 2.48 + 10.2 | Industry standard observability stack. Datadog is excellent but expensive; this is free and self-hosted. |
| Tracing | OpenTelemetry + Jaeger | latest | Vendor-neutral instrumentation. Spans across all services for full request tracing. |
| Auth | JWT (HS256) + bcrypt | — | Stateless tokens with bcrypt password hashing (work factor 12). |
| Rate limiting | SlowAPI + Redis | — | Redis-backed so limits are shared across replicas. |
| Logging | structlog | — | Structured JSON logging with context variables. Standard logging is unstructured and hard to query. |
| Container runtime | Docker + Compose | 24+ | Universal local development standard. |
| Kubernetes | K8s 1.30+ | — | Production deployment with HPA, NetworkPolicy, PDB. |

---

## 5. Prerequisites

Verify all prerequisites before cloning the repository. Running with wrong versions is the most common source of "it works on my machine" problems.

**Docker**
```bash
docker --version
# Required: Docker 24.0.0 or higher
# Install: https://docs.docker.com/get-docker/
```

**Docker Compose Plugin** (note: `docker compose`, not `docker-compose`)
```bash
docker compose version
# Required: v2.20.0 or higher
# The v1 `docker-compose` binary is deprecated and will not work with this project
```

**Python** (for running scripts locally, not required if using container exec)
```bash
python3 --version
# Required: 3.11.x
# Install via pyenv: pyenv install 3.11.8 && pyenv local 3.11.8
```

**make**
```bash
make --version
# Required: GNU Make 4.0+
# macOS: brew install make
# Ubuntu: apt install make
```

**kubectl** (required for Kubernetes deployment only)
```bash
kubectl version --client
# Required: 1.28+
# Install: https://kubernetes.io/docs/tasks/tools/
```

**Minimum host machine resources for the full Docker Compose stack:**
- CPU: 4 cores (8 recommended)
- RAM: 16 GB (8 GB minimum — Kafka + Airflow + MLflow are memory-hungry)
- Disk: 20 GB free (Docker images + volumes)

If your machine has less than 8 GB RAM, deploy only the core services by commenting out `airflow-webserver`, `airflow-scheduler`, and `mlflow` from `docker-compose.yml` during local development.

---

## 6. Local Development Setup

Follow these steps in exact order. Each step depends on the previous one completing successfully.

**Step 1 — Clone the repository**
```bash
git clone https://github.com/YOUR_USERNAME/drift-detector.git
cd drift-detector
```

**Step 2 — Create your environment file**
```bash
cp .env.example .env
```

Open `.env` in your editor and fill in every variable. The secrets validator will block startup if any required variable is empty. Generate strong secrets with:
```bash
# Run once per secret — use the output as your value
python3 -c "import secrets; print(secrets.token_hex(32))"
```

At minimum, set: `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `SECRET_KEY`, and `MODEL_VERSION=v1.0.0`. You can leave Slack and PagerDuty credentials blank for local development — alerts will log to console instead.

**Step 3 — Start the data layer**
```bash
make up
```

This starts only PostgreSQL, Redis, Zookeeper, and Kafka. All four must show `healthy` before proceeding:
```bash
docker compose ps
# NAME                    STATUS
# drift-postgres          running (healthy)
# drift-redis             running (healthy)
# drift-zookeeper         running (healthy)
# drift-kafka             running (healthy)
```

If Kafka stays in `starting` for more than 90 seconds, check Zookeeper first:
```bash
docker compose logs zookeeper | tail -20
# Look for: "binding to port 0.0.0.0/0.0.0.0:2181"
```

**Step 4 — Run database migrations**
```bash
make migrate
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial schema
```

If you see `Target database is not up to date` or `relation already exists`, you have a stale volume from a previous run. Reset with:
```bash
docker compose down -v   # destroys volumes — all data is lost
make up
make migrate
```

**Step 5 — Load reference baselines**
```bash
make load-baselines
```

This reads the sample CSV files from `data/baselines/` and inserts reference distributions for four features: `age`, `income`, `credit_score`, and `tenure`. Expected output:
```
Feature        Samples   Status
age            1000      inserted
income         1000      inserted
credit_score   1000      inserted
tenure         1000      inserted
```

**Step 6 — Create your admin user**
```bash
make create-admin
```

You will be prompted for username, password, and role. The password must be at least 16 characters and contain uppercase, lowercase, a digit, and a special character. Save these credentials — there is no reset flow.

**Step 7 — Start all remaining services**
```bash
make up
```

Run `docker compose ps` and wait for all services to show `healthy`. Airflow and MLflow take 2–3 minutes to initialise their internal databases.

**Step 8 — Open the dashboard**
```bash
open https://localhost
# or navigate manually in your browser
```

Accept the self-signed certificate warning. Log in with the credentials from Step 6.

**Step 9 — Verify Grafana**
```bash
make verify-grafana
# Expected: "All targets healthy" and "Dashboard found: ML Drift Detection — Operations"
```

Open `http://localhost:3000` and log in with the `GRAFANA_ADMIN_PASSWORD` from your `.env` file.

**Step 10 — Simulate drift**
```bash
make simulate-drift
```

This sends 2,000 synthetic inference requests — the first 1,000 drawn from the reference distribution, the second 1,000 drawn from a distribution shifted by 2 standard deviations. Watch the dashboard. Within 60–90 seconds you should see PSI scores climbing, the distribution histogram shifting, and the first alerts appearing in the alert log.

---

## 7. Environment Variables

All environment variables are defined in `.env.example`. This section documents every variable, its purpose, and its valid values. Variables marked **Required** will cause startup failure if absent or empty.

### Core Application

| Variable | Required | Default | Description | Example |
|----------|----------|---------|-------------|---------|
| `SECRET_KEY` | Yes | — | JWT signing key. Generate with `secrets.token_hex(64)`. Minimum 64 characters. | `a3f7c2...` |
| `MODEL_VERSION` | Yes | — | Identifier for the current production model. Used as the baseline lookup key. | `v1.0.0` |
| `ALLOWED_ORIGINS` | Yes | — | Comma-separated list of origins allowed by CORS. No wildcards in production. | `https://yourdomain.com` |
| `DASHBOARD_HOST` | No | `localhost` | Used in create_admin_user.py to print the login URL. | `yourdomain.com` |
| `JWT_EXPIRY_HOURS` | No | `8` | JWT token lifetime in hours. | `8` |
| `BASELINE_WARMUP_MIN_SAMPLES` | No | `500` | Minimum live samples before auto-registering a new model version's baselines. Lower = faster but less statistically reliable. | `500` |

### Database

| Variable | Required | Default | Description | Example |
|----------|----------|---------|-------------|---------|
| `POSTGRES_HOST` | Yes | — | PostgreSQL hostname. Use Docker Compose service name `postgres` for local dev. | `postgres` |
| `POSTGRES_PORT` | No | `5432` | PostgreSQL port. | `5432` |
| `POSTGRES_DB` | Yes | — | Database name. | `drift_detector` |
| `POSTGRES_USER` | Yes | — | Database user. | `drift_user` |
| `POSTGRES_PASSWORD` | Yes | — | Database password. Minimum 32 characters. | `generated_secret` |

### Redis

| Variable | Required | Default | Description | Example |
|----------|----------|---------|-------------|---------|
| `REDIS_HOST` | Yes | — | Redis hostname. Use `redis` for local dev. | `redis` |
| `REDIS_PORT` | No | `6379` | Redis port. | `6379` |
| `REDIS_PASSWORD` | Yes | — | Redis AUTH password. Minimum 32 characters. | `generated_secret` |
| `REDIS_DB` | No | `0` | Redis logical database index. | `0` |

### Kafka

| Variable | Required | Default | Description | Example |
|----------|----------|---------|-------------|---------|
| `KAFKA_BOOTSTRAP_SERVERS` | Yes | — | Comma-separated Kafka broker addresses. | `kafka:9092` |
| `KAFKA_SASL_USERNAME` | Yes | — | SASL username for broker authentication. | `drift_producer` |
| `KAFKA_SASL_PASSWORD` | Yes | — | SASL password. | `generated_secret` |
| `KAFKA_SASL_MECHANISM` | No | `SCRAM-SHA-512` | SASL mechanism. Use `PLAIN` for Upstash. | `SCRAM-SHA-512` |
| `KAFKA_SASL_ENABLED` | No | `true` | Set to `false` in test environments only. | `true` |
| `CIRCUIT_BREAKER_SERVICE_NAME` | No | `kafka-producer` | Identifier for the Redis circuit breaker state keys. | `kafka-producer` |

### Alerting

| Variable | Required | Default | Description | Example |
|----------|----------|---------|-------------|---------|
| `SLACK_WEBHOOK_URL` | No | — | Slack incoming webhook URL. Alerts log to console if absent. | `https://hooks.slack.com/...` |
| `PAGERDUTY_ROUTING_KEY` | No | — | PagerDuty Events API v2 routing key. Critical alerts only. | `abc123...` |

### MLflow

| Variable | Required | Default | Description | Example |
|----------|----------|---------|-------------|---------|
| `MLFLOW_TRACKING_URI` | Yes | — | MLflow server URI. | `http://mlflow:5000` |
| `MLFLOW_EXPERIMENT_NAME` | No | `drift-triggered-retrain` | MLflow experiment to log retrain runs under. | `drift-triggered-retrain` |

### Grafana

| Variable | Required | Default | Description | Example |
|----------|----------|---------|-------------|---------|
| `GRAFANA_ADMIN_PASSWORD` | Yes | — | Grafana admin user password. Minimum 12 characters. Do not use `admin`. | `generated_secret` |

---

## 8. Automatic Baseline Registration

### The problem with manual baselines

In a system where models are deployed continuously — sometimes multiple times per day — requiring an engineer to manually run `make load-baselines` every time a new model version goes to production is a reliability failure. It means drift detection has a blind spot during the period between model promotion and baseline loading. For a fast-moving team, that window can be hours.

### How auto-registration works

The interceptor's `BaselineRegistrar` solves this transparently. When a request arrives tagged with a `model_version` the system has never seen, the interceptor begins silently accumulating that version's feature values in a warm-up buffer stored in Redis. Each feature gets its own buffer. Once any feature's buffer reaches `BASELINE_WARMUP_MIN_SAMPLES` samples, the registrar automatically computes the reference distribution from the buffered data, inserts it into `feature_baselines`, and notifies all other services via the `baseline.registered` Kafka topic.

### The warm-up sample count tradeoff

`BASELINE_WARMUP_MIN_SAMPLES` defaults to 500. This is intentionally lower than the 1,000 samples used by `load_baselines.py`. The rationale: manually-loaded baselines are computed from carefully curated training data, so a higher bar is appropriate. Auto-registered baselines come from live traffic, which by definition represents the model's actual deployment context. 500 samples from real production traffic is statistically sufficient to build a reliable KDE and PSI bin structure for most features, while keeping the registration latency (time from first request to active monitoring) under a few minutes for typical traffic volumes.

Increasing `BASELINE_WARMUP_MIN_SAMPLES` to 1,000 or 2,000 gives a more statistically stable reference but delays drift monitoring for the new model version proportionally. Tune this based on your traffic volume.

### Multi-replica safety

When the interceptor runs as multiple Kubernetes replicas (as it does in production), all replicas receive inference traffic simultaneously. Without coordination, every replica would independently detect that the buffer is full and attempt to insert a baseline row at the same moment, causing duplicate inserts or race conditions.

The registrar uses a Redis distributed lock (`SET NX EX 60` on `baseline_reg_lock:{model_version}:{feature_name}`) to ensure exactly one replica wins the registration race. The replica that acquires the lock registers the baseline and then deletes the lock. All other replicas find the lock already set, see the registration complete on their next loop, and add the version to their `_known_versions` set.

### Cross-service cache invalidation

The processor and alerter both cache baselines in memory at startup for performance. When a new baseline is auto-registered, those caches are stale until the services restart — which could mean drift scoring continues against a non-existent baseline for the new model version.

The `baseline.registered` Kafka topic solves this. When the registrar successfully inserts a new baseline, it publishes a `BaselineRegisteredEvent` to this topic. Both the processor and alerter have Faust agents consuming this topic. On receiving an event, they immediately re-fetch the affected `(feature_name, model_version)` baseline from PostgreSQL and update their in-memory cache. The lag between registration and active monitoring is typically under 5 seconds.

### Verifying auto-registration is working

After deploying a new model version (change `MODEL_VERSION` in your environment and restart the interceptor), monitor registration progress:

```bash
# Watch for registration log lines
docker compose logs -f drift-interceptor | grep "Auto-registered baseline"

# Check the Prometheus metric in Grafana or via curl
curl -s http://localhost:9090/api/v1/query?query=drift_baselines_auto_registered_total \
  | python3 -m json.tool

# Verify the row appeared in PostgreSQL
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -c "SELECT feature_name, model_version, sample_count, created_by FROM feature_baselines ORDER BY computed_at DESC LIMIT 10;"
```

---

## 9. Production Deployment

### Option A — Single VM with Docker Compose

Recommended for: portfolio demos, staging environments, small-scale production (< 1,000 requests/min).

**Minimum VM specifications:**
- CPU: 8 vCPUs
- RAM: 32 GB
- Disk: 500 GB SSD
- OS: Ubuntu 24

### Option B — Render (PaaS)
1. Push your repository to GitHub.
2. We have provided a `render.yaml` Blueprint.
3. This blueprint defines Web Services (`drift-interceptor`, `drift-dashboard`), Background Workers (`drift-processor`, `drift-alerter`), and a Managed Redis instance.
4. Supply your Neon `DATABASE_URL` and managed Kafka strings as environment variables during the Render dashboard setup.
5. Render handles build and deployment automatically.

### Option C — DigitalOcean (Managed App Platform)
1. Push your repository to GitHub.
2. In DigitalOcean, create a new **App** and select your repository.
3. Configure `drift-interceptor` and `drift-dashboard` as Web Services. Configure `drift-processor` and `drift-alerter` as Workers.
4. Add a Managed PostgreSQL and Redis cluster.
5. Inject the connection strings as environment variables.

---

## 10. Secrets Management

- **`.env` files**: Used exclusively for local development. Never commit `.env`.
- **Render/DigitalOcean**: Use the built-in Environment Variables / Secret Management interfaces.
- **Kubernetes**: Use `SealedSecrets` or an External Secrets Operator pointing to AWS Secrets Manager / HashiCorp Vault.

---

## 11. Adding a New Model

1. Train and serialize your model.
2. Determine the feature schema (e.g., `["age", "income", "credit_score"]`).
3. Generate a reference baseline using the training dataset and `scripts/load_baselines.py`.
4. (Optional) Alternatively, let the **Automatic Baseline Registration** feature automatically register the baseline once `BASELINE_WARMUP_MIN_SAMPLES` are collected.
5. Send inference traffic to the interceptor using the new `model_version`.

---

## 12. Alert Configuration

Alerting rules are stored in the PostgreSQL database.
By default, the `rule_engine.py` evaluates:
- `KL Divergence > 0.15`
- `PSI > 0.20`
- `MMD p-value < 0.05`

Modify these thresholds directly in the database or via the `load_baselines.py` script.

---

## 13. Dashboard Guide

The bespoke React/Chart.js dashboard is available at `/`.
- View live ingestion rates and alert streams via WebSocket.
- Review historical drift visualizations.
- **Authentication:** Run `make create-admin` (which securely hashes using raw `bcrypt`) to create an admin user.

---

## 14. Grafana Dashboard

Grafana is provisioned natively via `drift.json`.
- Contains 13 panels.
- Tracks `KL divergence`, `PSI`, `MMD p-value`.
- Tracks system telemetry: `drift_interceptor_requests_total`, Kafka lag, Postgres connections.

---

## 15. Redis Key Reference

| Key Pattern | Purpose |
|-------------|---------|
| `circuit_breaker:{service_name}:state` | Open/half_open/closed state |
| `circuit_breaker:{service_name}:failure_count` | Continuous failures |
| `alert_dedup:{feature_name}:{detector_type}` | SET NX TTL lock for deduplication |
| `baseline_warmup:{model_version}:{feature_name}` | RPUSH list of live inference values |
| `baseline_reg_lock:{model_version}:{feature_name}` | SET NX EX lock to prevent race conditions |

---

## 16. Runbook

**Issue: UndefinedTableError on startup**
*Resolution:* Fixed! We implemented a synchronous `common.bootstrap` utility that runs `Base.metadata.create_all` safely and idempotently prior to the Faust event loop starting.

**Issue: Login Failing on Dashboard**
*Resolution:* Fixed! We removed the buggy `passlib` dependency and implemented raw `bcrypt==4.1.2` for safe password hashing compatible with Python 3.11.

---

## 17. Security Hardening Checklist

- [x] Non-root Docker containers (`USER 1001`).
- [x] Passwords securely hashed with `bcrypt`.
- [x] Internal services communicate over isolated Docker bridge network.
- [x] JWT tokens with 8-hour expiry and strict origin checking.
- [x] SQL Injection protected by SQLAlchemy ORM parametrised queries.

---

## 18. Performance Characteristics

- **Interceptor Latency:** < 2ms p99 overhead.
- **Event Loop Threading:** Fully async ingestion to Kafka.
- **Processor Windows:** Faust safely handles tumbling 1000-sample windows. State is backed by RocksDB to prevent memory overflow.
- **Database:** Serverless Neon Postgres provides scalable connection pooling (PgBouncer).

---

## 19. Testing

```bash
make test
make test-auto-baseline
```

---

## 20. Contributing

PRs are welcome. Please ensure `mypy --strict` and `bandit` pass before requesting a review.

---

## 21. License

MIT License. See `LICENSE` for details.