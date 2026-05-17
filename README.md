<div align="center">

# Real-Time E-Commerce Analytics Platform

**A production-grade data engineering platform built from scratch — streaming ingestion, SQL transformations, ML churn prediction, A/B testing, and a live business intelligence dashboard, all orchestrated and containerised.**

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Apache Airflow](https://img.shields.io/badge/Airflow-2.7.3-017CEE?style=flat-square&logo=apacheairflow&logoColor=white)](https://airflow.apache.org)
[![dbt](https://img.shields.io/badge/dbt-1.7.4-FF694B?style=flat-square&logo=dbt&logoColor=white)](https://getdbt.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.29-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)](https://streamlit.io)
[![Apache Spark](https://img.shields.io/badge/Apache_Spark-3.5-E25A1C?style=flat-square&logo=apachespark&logoColor=white)](https://spark.apache.org)
[![Docker](https://img.shields.io/badge/Docker_Compose-8-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)

</div>

---

## Screenshots

### Live Dashboard
<!-- SCREENSHOT: Full dashboard overview page showing KPI tiles, revenue trend chart, and geo map -->
> *Place screenshot here: `docs/screenshots/dashboard_overview.png`*

### Customer Analytics — RFM Segments & Churn Leaderboard
<!-- SCREENSHOT: Customer page with segment radar chart, RFM distribution, and churn risk table -->
> *Place screenshot here: `docs/screenshots/customer_analytics.png`*

### A/B Testing — GrowthBook Experiment Dashboard
<!-- SCREENSHOT: GrowthBook UI showing churn-discount-v1 experiment with 50/50 split and conversion metrics -->
> *Place screenshot here: `docs/screenshots/growthbook_experiment.png`*

### Airflow DAG Graph
<!-- SCREENSHOT: Airflow UI showing daily_analytics_dag with all task nodes and dependencies -->
> *Place screenshot here: `docs/screenshots/airflow_dag.png`*

### dbt Lineage Graph
<!-- SCREENSHOT: `dbt docs serve` lineage graph showing sources → staging → intermediate → marts -->
> *Place screenshot here: `docs/screenshots/dbt_lineage.png`*

### FastAPI Swagger UI
<!-- SCREENSHOT: /docs page showing all 25+ endpoint groups -->
> *Place screenshot here: `docs/screenshots/api_docs.png`*

---

## What This Is

This platform simulates a full e-commerce data stack — the kind of system a mid-sized company would run across multiple teams. Every component was chosen to solve a real data problem:

| Problem | Solution |
|---|---|
| Raw events need to land in a database fast | Kafka producer → Python consumer → PostgreSQL |
| Analytics SQL is duplicated across DAGs | dbt models with staging → intermediate → marts layers |
| "Who will churn next month?" | XGBoost model trained on 7 RFM features, AUC **0.9685** |
| Knowing who churns ≠ preventing churn | GrowthBook A/B experiment: 10% discount offer to high-risk users |
| OLTP scans kill DB performance for Spark jobs | Daily Parquet export to MinIO; Spark reads from object storage |
| Manual cohort analysis is slow | PySpark job computes 435-row cohort retention matrix automatically |
| Dashboard data goes stale | Airflow materialized view refresh + Redis TTL caching |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           DATA SOURCES                                   │
│          event_generator.py  ·  seed_transactions.py (162K rows)         │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ Kafka Topics
                    ┌───────────▼───────────┐
                    │   Apache Kafka 7.5     │
                    │  user_events           │
                    │  transactions          │
                    └───────────┬───────────┘
                                │
              ┌─────────────────▼──────────────────┐
              │         transaction_consumer.py      │
              │         (Python → PostgreSQL)         │
              └─────────────────┬──────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────────┐
│                          PostgreSQL 15                                    │
│  Star Schema · Monthly Partitions · Materialized Views · Indexes          │
│  10K users · 1K products · 162K transactions · RFM segments · Churn scores│
└──────────┬───────────────────────────────────────┬───────────────────────┘
           │                                       │
    ┌──────▼──────┐                        ┌───────▼───────┐
    │  dbt Core   │                        │  MinIO (S3)   │
    │  Staging    │                        │  Parquet Lake │
    │  Intermediate│                       │  (daily export)│
    │  Marts      │                        └───────┬───────┘
    └──────┬──────┘                                │
           │                               ┌───────▼───────┐
    ┌──────▼──────────────────┐            │  Apache Spark  │
    │   Apache Airflow 2.7.3  │            │  Cohort        │
    │   7 DAGs orchestrate:   │            │  Retention Job │
    │   • dbt build           │            └───────┬───────┘
    │   • ML retraining       │                    │
    │   • Parquet export      │◄───────────────────┘
    │   • AB metrics          │  writes cohort_retention → Postgres
    └──────┬──────────────────┘
           │
    ┌──────▼──────────────────┐
    │  FastAPI + Redis Cache   │
    │  25+ REST endpoints      │
    │  XGBoost churn scoring   │
    │  GrowthBook A/B SDK      │
    └──────┬──────────────────┘
           │
    ┌──────▼──────────────────┐
    │   Streamlit Dashboard    │
    │   5 pages · auto-refresh │
    │   Plotly charts          │
    └─────────────────────────┘
```

<!-- DIAGRAM: Replace ASCII art above with a clean architecture diagram image -->
> *Place architecture diagram here: `docs/architecture.png`*

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **Database** | PostgreSQL 15 | Star schema, monthly partitions, materialized views, NTILE window functions |
| **Streaming** | Apache Kafka 7.5 | Decouples producers from consumers; enables replay |
| **Transformation** | dbt Core 1.7.4 | SQL-as-code, lineage graph, built-in tests, staging→marts layers |
| **Orchestration** | Apache Airflow 2.7.3 | DAG dependencies, retries, scheduling, data quality gates |
| **Object Storage** | MinIO (S3-compatible) | Decouples Spark compute from OLTP Postgres; Parquet for columnar reads |
| **Batch Compute** | Apache Spark 3.5 | Cohort retention across 162K rows with self-join; PySpark DataFrame API |
| **API** | FastAPI + Pydantic v2 | Auto-generated OpenAPI docs, async-ready, type-safe request/response |
| **Cache** | Redis 7 | 60s–3600s TTL per endpoint; connection pool reuse |
| **ML** | XGBoost + scikit-learn | 7-feature churn model, AUC 0.9685; weekly Airflow retraining gate |
| **A/B Testing** | GrowthBook SDK | Deterministic FNV hash assignment, zero-latency inline evaluation |
| **Dashboard** | Streamlit 1.29 + Plotly | 5-page BI tool; auto-refresh every 60s; radar, funnel, geo charts |
| **Infrastructure** | Docker Compose | 9-service stack: Postgres, Redis, API, Dashboard, Airflow, MinIO, Spark, Mongo, GrowthBook |

---

## Project Structure

```
ecommerce-analytics/
│
├── docker/
│   ├── docker-compose.yml          # 9-service stack definition
│   ├── Dockerfile.api              # FastAPI + XGBoost image
│   ├── Dockerfile.dashboard        # Streamlit image
│   └── Dockerfile.spark            # PySpark + Java image
│
├── database/
│   └── postgres/
│       ├── schema.sql              # Star schema, partitions, indexes, materialized views
│       ├── seed_data.sql           # 10K users, 1K products, personas
│       ├── seed_transactions.py    # 162K Weibull-distributed transactions
│       ├── migrations/
│       │   ├── 001_phase3_tables.sql   # daily_report_log, cohort_retention
│       │   └── 002_ab_testing.sql      # ab_assignments, ab_experiment_metrics
│       └── queries/
│           ├── rfm_segmentation.sql
│           ├── cohort_analysis.sql
│           ├── recommendations.sql
│           └── realtime_dashboard.sql
│
├── dbt/
│   ├── dbt_project.yml             # staging=view, marts=table
│   ├── profiles.yml                # env_var() credentials
│   ├── models/
│   │   ├── staging/
│   │   │   ├── stg_transactions.sql  # Cast + filter raw transactions
│   │   │   ├── stg_users.sql         # Filter null users
│   │   │   └── schema.yml            # Source definitions + tests
│   │   ├── intermediate/
│   │   │   └── int_rfm_scores.sql    # NTILE(5) R/F/M window functions
│   │   └── marts/
│   │       ├── mart_rfm_segments.sql     # Segment labels (Champions → Lost)
│   │       ├── mart_churn_features.sql   # 7 ML features centralised
│   │       ├── mart_daily_snapshot.sql   # Daily KPI aggregates
│   │       └── schema.yml                # Not-null, unique, accepted_values tests
│   └── tests/
│       └── assert_no_negative_revenue.sql  # Singular data test
│
├── airflow/
│   └── dags/
│       ├── hourly_refresh_dag.py       # Refresh materialized views (every hour)
│       ├── data_quality_dag.py         # 7 quality checks (daily 01:30)
│       ├── daily_analytics_dag.py      # dbt build + RFM/churn write-back (daily 02:00)
│       ├── export_to_minio_dag.py      # Postgres → Parquet → MinIO (daily 03:00)
│       ├── ab_metrics_dag.py           # A/B conversion metrics (daily 04:00)
│       ├── model_retraining_dag.py     # XGBoost retrain + AUC gate (weekly)
│       └── daily_transactions_dag.py   # Transaction ingestion trigger
│
├── spark/
│   └── jobs/
│       └── cohort_retention.py     # MinIO Parquet → cohort matrix → Postgres
│
├── api/
│   ├── main.py                     # FastAPI app, lifespan, middleware
│   ├── config.py                   # pydantic-settings
│   ├── dependencies.py             # DB pool, Redis, cache helpers
│   ├── models/
│   │   ├── schemas.py              # 20+ Pydantic response models
│   │   └── ml_models.py            # XGBoost loader + heuristic fallback
│   └── routers/
│       ├── health.py               # /health, /health/db, /health/redis
│       ├── customers.py            # RFM, churn, segments, at-risk, top
│       ├── recommendations.py      # User CF, item CF, trending
│       ├── products.py             # Top products, categories, inventory
│       ├── dashboard.py            # KPIs, revenue, geo, payments
│       └── ab_testing.py           # GrowthBook experiment offer + results
│
├── dashboards/
│   ├── streamlit_app.py            # Home + sidebar
│   ├── api_client.py               # HTTP wrapper for all endpoints
│   ├── components/
│   │   ├── style.py                # CSS, colour constants, badges
│   │   ├── kpi_tiles.py            # KPI card components
│   │   └── charts.py               # Plotly chart builders
│   └── pages/
│       ├── 01_Overview.py          # Live KPIs, revenue trend, geo map
│       ├── 02_Customers.py         # RFM segments, churn leaderboard
│       ├── 03_Recommendations.py   # Trending + collaborative filtering
│       ├── 04_Products.py          # Top products, inventory alerts
│       └── 05_Explorer.py          # Customer + product deep-dive
│
├── kafka/
│   ├── producers/event_generator.py   # Simulates user sessions
│   └── consumers/transaction_consumer.py
│
├── models/                         # Trained XGBoost model (gitignored)
├── tests/                          # pytest suite
├── render.yaml                     # Render.com deployment manifest
└── requirements*.txt               # Pinned dependencies per service
```

---

## dbt Transformation Layer

Three-layer medallion architecture: raw → clean → business-ready.

```
Sources (PostgreSQL)
    │
    ├── stg_transactions   [VIEW]   Cast dates, filter nulls/negatives
    └── stg_users          [VIEW]   Filter null user_id rows
            │
            └── int_rfm_scores     [VIEW]   NTILE(5) window functions
                        │                   for recency / frequency / monetary
                        │
            ┌───────────┼────────────────────────┐
            │           │                        │
  mart_rfm_segments   mart_churn_features   mart_daily_snapshot
     [TABLE]              [TABLE]               [TABLE]
  12 segment labels    7 ML features        Daily KPI aggregates
  (Champions→Lost)     centralised          (revenue, orders, AOV)
```

<!-- SCREENSHOT: dbt docs lineage graph -->
> *Run `dbt docs generate && dbt docs serve` then screenshot the lineage graph here: `docs/screenshots/dbt_lineage.png`*

### dbt Tests

| Test Type | What It Catches |
|---|---|
| `not_null` on `user_id` | Orphaned transaction records |
| `unique` on `user_id` in marts | Duplicate aggregation rows |
| `accepted_values` on `customer_segment` | Typos in CASE WHEN labels (12 valid segments) |
| `assert_no_negative_revenue` (singular) | Corrupt or refund transactions leaking into analytics |

---

## Machine Learning Pipeline

### Churn Model

- **Algorithm**: XGBoost classifier
- **Label**: No purchase in the **next 30 days** from snapshot date (forward-looking)
- **Features** (all computed in `mart_churn_features`):

| Feature | Description |
|---|---|
| `recency_days` | Days since last purchase |
| `frequency` | Total number of orders |
| `monetary` | Total spend (£) |
| `avg_order_value` | monetary / frequency |
| `tenure_days` | Days since first purchase |
| `purchase_velocity` | Orders per active month |
| `recency_ratio` | recency_days / tenure_days |

- **Performance**: AUC **0.9685** on held-out test set
- **Retraining**: Weekly Airflow DAG gates on AUC ≥ 0.70 before replacing the production model
- **Serving**: Model loaded at API startup via `load_churn_model()`; scores returned in `/customers/{id}/churn`

### RFM Segmentation

11 customer segments derived from NTILE(5) R/F/M scores:

| Segment | R | F | M |
|---|---|---|---|
| Champions | 5 | 5 | 5 |
| Loyal Customers | ≥4 | ≥4 | — |
| Potential Loyalists | ≥3 | 3–4 | — |
| Recent Customers | 5 | ≤1 | — |
| Promising | 4 | ≤1 | — |
| Needing Attention | ≤3 | ≤3 | ≤3 |
| About To Sleep | ≤3 | ≤2 | ≤2 |
| At Risk | ≤2 | ≥4 | ≥4 |
| Can't Lose Them | ≤1 | 5 | 5 |
| Hibernating | ≤2 | ≤2 | ≤2 |
| Lost | 1 | 1 | 1 |

---

## A/B Testing with GrowthBook

```
High-risk user (churn_risk ≥ 0.60)
            │
  GrowthBook FNV hash(user_id + "churn-discount-v1")
            │
   ┌────────┴────────┐
   │                 │
 control           discount_10pct
 (50%)             (50%)
   │                 │
no offer        show 10% discount
   │                 │
   └────────┬────────┘
            │
   ab_assignments  ←  ON CONFLICT DO NOTHING
   (sticky: same user always same variant)
            │
   ab_experiment_metrics  ←  nightly Airflow DAG
   (conversion = purchase within 7 days)
            │
   GrowthBook UI reads Postgres → computes
   statistical significance + lift
```

**Key design decisions:**
- Assignment is **deterministic** — same user always gets the same variant across sessions
- First assignment wins (`ON CONFLICT DO NOTHING`) — no variant switching mid-experiment
- Conversion window is 7 days post-assignment
- GrowthBook runs **inline** (no round-trip to server on each API call) — zero added latency

---

## Airflow DAGs

```
Timeline each day:
01:30  data_quality_dag     ─ 7 checks (nulls, orphans, anomalies, stale views)
02:00  daily_analytics_dag  ─ dbt build → write RFM/churn scores back to users table
03:00  export_to_minio_dag  ─ export 4 tables to Parquet in MinIO
04:00  ab_metrics_dag       ─ compute A/B conversion rates, upsert metrics table

Every hour:
       hourly_refresh_dag   ─ REFRESH MATERIALIZED VIEW (daily_metrics, user_metrics)

Weekly (Sunday):
       model_retraining_dag ─ retrain XGBoost, gate on AUC ≥ 0.70

On demand:
       spark cohort job     ─ docker compose --profile spark run --rm spark
```

<!-- SCREENSHOT: Airflow graph view of daily_analytics_dag -->
> *Place Airflow DAG screenshot here: `docs/screenshots/airflow_dag.png`*

### daily_analytics_dag Task Flow

```
check_data_freshness
        │
  ┌─────┴──────┐
  │            │
quality_pass  quality_fail
  │            │
  └─────┬──────┘
        │
    dbt_build
    (staging → intermediate → marts)
        │
        ├──► apply_rfm_to_users ──► apply_churn_scores ──┐
        │                                                  │
        └──► apply_snapshot_to_log ────────────────────────┤
                                                           │
                                                  notify_completion
```

> **Why sequential for RFM then churn?** Both UPDATE the `users` table. Running them in parallel caused deadlocks — row lock acquisition order differed between the two UPDATE statements. Sequential execution eliminates the race.

---

## MinIO + Apache Spark

### Why MinIO?

PostgreSQL is an OLTP database — not designed for large sequential scans. Exporting daily snapshots as Parquet to MinIO decouples the Spark compute layer from the operational database. Spark reads columnar Parquet from MinIO; Postgres is never touched.

### Cohort Retention

The PySpark job computes a **monthly cohort retention matrix**: for each cohort of users who made their first purchase in month M, what percentage were still purchasing N months later?

```python
# Core logic (simplified)
purchases = df.select("user_id", date_trunc("month", "transaction_date").alias("month")).distinct()
cohorts   = purchases.groupBy("user_id").agg(F.min("month").alias("cohort_month"))
joined    = purchases.join(cohorts, on="user_id")
           .withColumn("months_since_first",
               F.months_between("purchase_month", "cohort_month").cast("int"))
```

Output: **435 rows** written to `cohort_retention` table in Postgres — ready for a heatmap visualisation.

```
       Months Since First Purchase
       0      1      2      3      4    ...
2023-01  100%   42%   31%   24%   19%
2023-02  100%   38%   29%   22%   ...
2023-03  100%   45%   33%   ...
...
```

---

## API Reference

Base URL: `http://localhost:8000` (Docker) · `https://<render-app>.onrender.com` (production)

### Health
| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Service health + version |
| GET | `/health/db` | PostgreSQL round-trip latency |
| GET | `/health/redis` | Redis round-trip latency |

### Dashboard KPIs
| Method | Endpoint | Description |
|---|---|---|
| GET | `/dashboard/kpi/realtime` | Last-hour KPIs (orders, revenue, AOV, new users) |
| GET | `/dashboard/kpi/today-vs-yesterday` | Day-over-day comparison with % change |
| GET | `/dashboard/kpi/daily` | 30-day daily trend |
| GET | `/dashboard/revenue/hourly` | Hourly revenue (last 24h) |
| GET | `/dashboard/revenue/by-country` | Revenue breakdown by country |
| GET | `/dashboard/customers/new-vs-returning` | New vs returning customer split |
| GET | `/dashboard/payments` | Payment method breakdown |

### Customers & ML
| Method | Endpoint | Description |
|---|---|---|
| GET | `/customers/{id}/rfm` | RFM scores + segment label |
| GET | `/customers/{id}/churn` | Churn probability + risk factor breakdown |
| GET | `/customers/segments` | All 11 segment summaries with counts |
| GET | `/customers/at-risk` | Paginated high-churn customers |
| GET | `/customers/top` | Top customers by lifetime value |

### Recommendations
| Method | Endpoint | Description |
|---|---|---|
| GET | `/recommendations/user/{id}` | Personalised user-based CF |
| GET | `/recommendations/similar/{id}` | Item-based CF (also-bought) |
| GET | `/recommendations/trending` | Top 20 products (last 24h) |

### Products
| Method | Endpoint | Description |
|---|---|---|
| GET | `/products/top` | Top products by revenue |
| GET | `/products/top/category` | Top categories |
| GET | `/products/inventory/alerts` | Low-stock alerts |
| GET | `/products/{id}` | Product detail + metrics |

### A/B Testing
| Method | Endpoint | Description |
|---|---|---|
| GET | `/experiment/offer/{user_id}` | Get variant + discount offer for user |
| GET | `/experiment/results` | Assignment counts + latest conversion metrics |

Full interactive docs at `/docs` (Swagger UI) and `/redoc`.

---

## Quick Start

### Prerequisites
- Docker Desktop
- Python 3.10+

### 1. Clone and configure

```bash
git clone https://github.com/Vis-3/Real-Time-E-Commerce-Analytics-Platform.git
cd Real-Time-E-Commerce-Analytics-Platform
cp .env.example .env          # edit if needed — defaults work for Docker
```

### 2. Start the full stack

```bash
cd docker
docker compose up -d
```

This starts 9 services: PostgreSQL, Redis, data seeder (162K transactions), FastAPI, Streamlit, Airflow, MinIO, MongoDB, and GrowthBook. The seeder runs once and exits.

Wait ~2 minutes for the seeder to finish, then:

| Service | URL | Credentials |
|---|---|---|
| Streamlit Dashboard | http://localhost:8501 | — |
| FastAPI Docs | http://localhost:8000/docs | — |
| Airflow UI | http://localhost:8080 | admin / admin |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |
| GrowthBook UI | http://localhost:3000 | create on first visit |

### 3. Train the churn model

```bash
pip install -r requirements.txt
python train_model.py
```

The model is saved to `models/churn_model.pkl` and mounted into the API container automatically.

### 4. Trigger the analytics pipeline

In Airflow UI (http://localhost:8080), unpause and trigger:
1. `daily_analytics_dag` — runs dbt, updates RFM + churn scores
2. `export_to_minio_dag` — exports Parquet to MinIO
3. `ab_metrics_dag` — computes A/B conversion metrics

### 5. Run the Spark cohort job (on demand)

```bash
cd docker
docker compose --profile spark run --rm spark
```

Writes **435 rows** of monthly cohort retention data to Postgres.

### 6. Development (without Docker)

```bash
# API
uvicorn api.main:app --port 8000 --reload

# Dashboard
cd dashboards && streamlit run streamlit_app.py

# Kafka event generator
cd kafka/producers && python event_generator.py --rate 10

# Kafka consumer
cd kafka/consumers && python transaction_consumer.py
```

---

## Data Model

```
users                        products
├── user_id (PK)             ├── product_id (PK)
├── country                  ├── product_name
├── persona                  ├── category
├── customer_segment (RFM)   ├── price
├── churn_risk_score         └── stock_quantity
├── rfm_r / rfm_f / rfm_m
└── total_lifetime_value

transactions (partitioned by month)
├── transaction_id (PK)
├── user_id (FK → users)
├── product_id (FK → products)
├── quantity
├── unit_price
├── total_amount
├── transaction_date
└── payment_method

ab_assignments                   ab_experiment_metrics
├── user_id (FK)                 ├── metric_date
├── experiment_key               ├── experiment_key
├── variant                      ├── variant
├── assigned_at                  ├── assigned_users
└── UNIQUE(user_id, experiment_key)  ├── converted_users
                                 └── conversion_rate

cohort_retention
├── cohort_month
├── months_since_first
└── retention_rate
```

---

## Performance

All measurements on Docker (WSL2, single machine). Production numbers account for network latency.

| Query | Local (warm cache) | Production estimate | Redis hit |
|---|---|---|---|
| Real-time KPI (last 1h) | 0.24 ms | 5–15 ms | ~1 ms |
| Single user RFM lookup | 0.075 ms | 2–5 ms | ~1 ms |
| 30-day daily KPIs (mat. view) | 0.077 ms | 1–5 ms | ~1 ms |
| Top 10 products (24h join) | 2.6 ms | 10–30 ms | ~1 ms |
| Churn leaderboard (2,945 users) | 7 ms | 20–60 ms | ~1 ms |
| RFM segment distribution | 3.1 ms | 10–25 ms | ~1 ms |

**Why it's fast:**
- Monthly table partitioning — last-hour queries prune to 1 partition regardless of total row count
- Materialized views (`daily_metrics`, `user_metrics`) — 30-day trend reads 182 pre-aggregated rows, not the full transactions table
- Redis TTL caching — hot endpoints serve from memory after the first request
- Connection pooling (`ThreadedConnectionPool`) — 2–10 persistent DB connections reused across requests

---

## Key Engineering Decisions

### Why dbt over inline SQL in Airflow DAGs?

Airflow DAGs with raw SQL strings have no lineage, no tests, and no version control ergonomics. dbt gives us:
- **Lineage graph** — visualise every dependency from source to mart
- **Built-in tests** — `not_null`, `unique`, `accepted_values` run as part of `dbt build`
- **Materialisation control** — staging as cheap VIEWs, marts as TABLEs for fast reads
- **`dbt build`** — runs each model then tests it before building downstream models; stops on failure

### Why XGBoost over logistic regression?

The churn dataset has non-linear relationships (a user who buys very infrequently but has very high AOV behaves differently from a frequent low-AOV buyer). XGBoost handles this without feature engineering; logistic regression needed polynomial terms and still scored 0.12 AUC lower.

### Why GrowthBook over a hand-rolled experiment flag?

A hand-rolled flag (e.g. `user_id % 2 == 0`) cannot be changed without a deploy, has no UI for stakeholders to monitor, and produces no statistical analysis. GrowthBook's SDK uses a deterministic FNV hash (same as a manual flag) but adds: experiment UI, feature flag overrides, and Postgres-backed metric analysis — all without touching the hot API path.

### Why MinIO + Parquet instead of querying Postgres directly from Spark?

Spark's Postgres JDBC driver reads all rows serially unless you configure partition predicates carefully. A 162K-row table with complex joins can lock rows or degrade API response times during a Spark scan. MinIO Parquet is columnar, partition-prunable, and completely isolated from the OLTP workload.

### Why sequential RFM → churn write-back instead of parallel?

Both UPDATE the `users` table. Running them in parallel caused deadlocks: row lock acquisition order differed between the two statements, creating a circular wait. Sequential execution eliminates the race condition at zero cost — churn update takes ~400ms.

---

## Deployment

### Docker (full stack — recommended for development)

Everything runs in Docker Compose. See [Quick Start](#quick-start) above.

### Render (API + dashboard — for production)

The `render.yaml` in the root defines two Render services:
- **API**: FastAPI served by uvicorn, connected to a Render Postgres instance and Redis
- **Dashboard**: Streamlit connected to the Render API via `API_BASE_URL`

> **Note:** Airflow, dbt, MinIO, Spark, and GrowthBook are Docker-only components. The Render deployment exposes the API and dashboard; the data pipeline runs on a separate server or is triggered manually.

```bash
# Deploy to Render via CLI
render up
```

---

## Challenges & Fixes

| Challenge | Root Cause | Fix |
|---|---|---|
| `dbt --project-dir` "No such option" | In dbt 1.x, `--project-dir` is a subcommand flag, not a global flag | Moved flag after `dbt build` |
| `dbt test` "relation stg_transactions does not exist" | `dbt test` runs against models that must already be built | Switched to `dbt build` (run then test in dependency order) |
| `apply_rfm_to_users` "Unknown hook type postgresql+psycopg2" | `AIRFLOW_CONN_` URI scheme determines conn_type; `postgresql+psycopg2://` is not registered | Changed to `postgres://` scheme |
| Deadlock between RFM and churn updates | Two parallel UPDATEs to the same table with different lock acquisition order | Chained tasks sequentially: `t_apply_rfm >> t_apply_churn` |
| `fillcolor` 8-digit hex invalid | Plotly does not accept `#rrggbbaa` format | Converted to `rgba(r,g,b,alpha)` via `_hex_to_rgba()` helper |
| GrowthBook `result.in_experiment` AttributeError | GrowthBook Python SDK uses camelCase | Fixed to `result.inExperiment` |
| PowerShell `<` redirection not supported | PowerShell reserves `<` for future use | Used `Get-Content file \| docker exec -i ...` |
| Airflow SIGTERM timeout on `wait_for_completion=True` | DAG was paused, blocking indefinitely | Set `wait_for_completion=False` (fire-and-forget) |

---

## Numbers at a Glance

| Metric | Value |
|---|---|
| Transactions | **162,233** (Weibull-distributed, persona-driven) |
| Users | **10,000** (8 behavioural personas) |
| Products | **1,000** across multiple categories |
| Churn model AUC | **0.9685** |
| API endpoints | **25+** |
| Airflow DAGs | **7** |
| dbt models | **6** (2 staging, 1 intermediate, 3 marts) |
| dbt tests | **10+** (schema + singular) |
| Cohort retention rows | **435** |
| A/B experiment | **50/50** split, churn_risk ≥ 0.60 threshold |
| Docker services | **9** |

---

## Requirements

- Docker Desktop (for the full stack)
- Python 3.10+ (for local development)
- Java 11+ (only for the Spark cohort job)

```bash
# Full install
pip install -r requirements.txt

# API only (Render deployment)
pip install -r requirements_api.txt

# Dashboard only
pip install -r requirements_dashboard.txt
```

---

<div align="center">

Built with PostgreSQL, FastAPI, dbt, Airflow, Spark, GrowthBook, and Streamlit.

</div>
