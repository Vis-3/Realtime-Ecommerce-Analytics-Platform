# E-Commerce Analytics Platform — End-to-End Setup & Testing

## Architecture Overview

```
Kafka Producer  →  Kafka  →  Spark Streaming  →  PostgreSQL
                                                      ↑
                                               Airflow DAGs
                                                      ↑
                                              FastAPI + Redis
                                                      ↑
                                           Streamlit Dashboard
```

**Services (Docker):** PostgreSQL · MongoDB · Redis · Zookeeper · Kafka · Airflow
**Local processes:** FastAPI (uvicorn) · Kafka Producer · Streamlit

---

## Prerequisites

```bash
# Install Python dependencies
cd ~/db_project/ecommerce-analytics
pip install -r requirements.txt
pip install streamlit-autorefresh pydantic-settings
```

---

## Step 1 — Start Infrastructure (Docker)

```bash
cd ~/db_project/ecommerce-analytics/docker
docker compose up -d
```

Wait ~30 seconds for all containers to initialise, then verify:

```bash
docker compose ps
```

Expected: all 6 containers show `running` or `healthy`.

| Container            | Port  | Purpose              |
|----------------------|-------|----------------------|
| ecommerce_postgres   | 5432  | Main database        |
| ecommerce_mongo      | 27017 | Event store          |
| ecommerce_redis      | 6379  | API cache            |
| ecommerce_zookeeper  | 2181  | Kafka coordination   |
| ecommerce_kafka      | 9092  | Event streaming      |
| ecommerce_airflow    | 8080  | DAG orchestration    |

### Verify PostgreSQL seeded correctly

```bash
docker exec ecommerce_postgres psql -U postgres -d ecommerce -c "
SELECT
  (SELECT COUNT(*) FROM users)        AS users,
  (SELECT COUNT(*) FROM products)     AS products,
  (SELECT COUNT(*) FROM transactions) AS transactions;
"
```

Expected: ~10,000 users · ~1,000 products · ~100,000 transactions.

### Verify Kafka topics exist

```bash
docker exec ecommerce_kafka \
  kafka-topics --bootstrap-server localhost:9092 --list
```

Expected topics: `user_events`, `transactions`.
If missing, create them:

```bash
docker exec ecommerce_kafka \
  kafka-topics --bootstrap-server localhost:9092 \
  --create --topic user_events --partitions 4 --replication-factor 1

docker exec ecommerce_kafka \
  kafka-topics --bootstrap-server localhost:9092 \
  --create --topic transactions --partitions 4 --replication-factor 1
```

---

## Step 2 — Start the FastAPI Server

Open a new terminal:

```bash
cd ~/db_project/ecommerce-analytics
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify it's up:

```bash
curl http://localhost:8000/health
# {"status":"healthy"}

curl http://localhost:8000/health/db
# {"status":"healthy","latency_ms":...}

curl http://localhost:8000/health/redis
# {"status":"healthy","latency_ms":...}
```

Interactive API docs: **http://localhost:8000/docs**

---

## Step 3 — Start the Streamlit Dashboard

Open a new terminal:

```bash
cd ~/db_project/ecommerce-analytics/dashboards
streamlit run streamlit_app.py
```

Open **http://localhost:8501** in your browser.

The sidebar shows live health dots for API / PostgreSQL / Redis.

---

## Step 4 — Start the Kafka Event Producer

Open a new terminal:

```bash
cd ~/db_project/ecommerce-analytics/kafka/producers
python event_generator.py --rate 5
```

`--rate 5` sends 5 events per second. You should see JSON events printed to stdout as they are produced.

---

## Step 5 — Start Spark Streaming Consumer (optional)

> Requires a local Spark installation or `pyspark` in your Python env.

Open a new terminal:

```bash
cd ~/db_project/ecommerce-analytics/spark/streaming
spark-submit \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.6.0 \
  kafka_consumer.py
```

This writes 5-second aggregates into the `realtime_metrics` table in PostgreSQL.

---

## Step 6 — Verify Airflow DAGs

Open **http://localhost:8080** — login: `admin` / `admin`

You should see 4 DAGs:

| DAG                    | Schedule       | Purpose                              |
|------------------------|----------------|--------------------------------------|
| `hourly_refresh`       | Every hour     | Refresh materialized views           |
| `data_quality_checks`  | Daily 01:30    | 7 data quality validations           |
| `daily_analytics`      | Daily 02:00    | RFM + churn score updates            |
| `model_retraining`     | Weekly (Sun)   | Retrain churn/RFM ML models          |

To trigger a DAG manually for testing:

```bash
docker exec ecommerce_airflow airflow dags trigger hourly_refresh_dag
docker exec ecommerce_airflow airflow dags trigger daily_analytics_dag
```

---

## End-to-End Test Checklist

### Dashboard pages

| Page | URL | What to verify |
|------|-----|----------------|
| Home | http://localhost:8501 | Health dots green, platform stats visible |
| Overview | .../01_Overview | KPI cards populated, revenue chart has data |
| Customers | .../02_Customers | Segment donut chart, churn leaderboard table |
| Recommendations | .../03_Recommendations | Trending products list, user rec lookup works |
| Products | .../04_Products | Top products chart, inventory alerts table |
| Explorer | .../05_Explorer | Customer lookup (try ID 1), product lookup (try ID 1) |

### API spot-checks

```bash
# Real-time KPIs
curl http://localhost:8000/dashboard/kpi/realtime | python3 -m json.tool

# Customer RFM profile
curl http://localhost:8000/customers/1/rfm | python3 -m json.tool

# Customer churn score
curl http://localhost:8000/customers/1/churn | python3 -m json.tool

# Personalised recommendations
curl http://localhost:8000/recommendations/user/1 | python3 -m json.tool

# Similar products
curl http://localhost:8000/recommendations/similar/1 | python3 -m json.tool

# Top products
curl http://localhost:8000/products/top?limit=5 | python3 -m json.tool

# Inventory alerts
curl http://localhost:8000/products/inventory/alerts | python3 -m json.tool

# Revenue by country
curl http://localhost:8000/dashboard/revenue/by-country | python3 -m json.tool
```

---

## Stopping Everything

```bash
# Stop Streamlit / FastAPI / Producer — Ctrl+C in each terminal

# Stop Docker services
cd ~/db_project/ecommerce-analytics/docker
docker compose down

# To also delete all data volumes (full reset):
docker compose down -v
```

---

## Troubleshooting

**FastAPI can't connect to PostgreSQL / Redis**
- Confirm Docker containers are running: `docker compose ps`
- Default connection: `postgresql://postgres:postgres@localhost:5432/ecommerce`

**Kafka producer throws `NoBrokersAvailable`**
- Kafka may still be starting. Wait 10s and retry.
- Check: `docker logs ecommerce_kafka | tail -20`

**Airflow shows no DAGs**
- DAG files are volume-mounted from `airflow/dags/`. Check `docker exec ecommerce_airflow airflow dags list`.

**Streamlit shows "unavailable" tiles**
- The API must be running (`uvicorn`) before the dashboard loads data.
- Check terminal running uvicorn for error traces.

**Churn model not loaded (API logs warning)**
- Normal on first run — `model_retraining_dag` hasn't run yet.
- The API falls back to a heuristic scorer automatically.
- Trigger the DAG manually: `docker exec ecommerce_airflow airflow dags trigger model_retraining_dag`
