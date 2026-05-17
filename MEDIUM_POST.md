# I Built a Real-Time E-Commerce Analytics Platform From Scratch — Here's What Actually Happened

**A five-phase deep dive into PostgreSQL partitioning, Kafka streaming, Airflow orchestration, and the bugs that nearly broke me. ~15 min read.**

---

I set out to build a production-grade analytics platform the way most side projects start: with a vague notion that it would be "useful" and a dangerous amount of free time. Five phases later, I have a system that ingests simulated user events through Kafka, stores them in a partitioned PostgreSQL schema, runs Airflow DAGs to refresh materialized views and score churn risk, serves 22 REST endpoints behind Redis caching, and visualises everything in a Streamlit dashboard with auto-refresh.

This post is not a tutorial. It's a post-mortem with working code. I'm going to walk through every architectural decision, every real bug I hit, and give you the honest ML assessment you never see in "building a data platform" posts.

---

## The Architecture at a Glance

Before diving in, here's the full data flow:

```
event_generator.py
       ↓
   Kafka Topics
(user_events / transactions — 4 partitions each)
       ↓
transaction_consumer.py
       ↓
  PostgreSQL 15
  (star schema, monthly partitions, materialized views)
       ↓
  Airflow DAGs
  (refresh, RFM scoring, quality checks, ML retraining)
       ↓
  FastAPI + Redis
  (22 endpoints, tiered TTL caching)
       ↓
Streamlit Dashboard
  (5 pages, Plotly dark theme, 60s auto-refresh)
```

The whole thing runs in Docker Compose. The stack: PostgreSQL 15, Apache Kafka (Confluent 7.5), Airflow 2.7.3, FastAPI, Redis 7, scikit-learn, Streamlit, and optionally PySpark for stream processing.

---

## Phase 1: PostgreSQL Star Schema and the Partition Trap

I started with a classic star schema — `users`, `products`, and a `transactions` table at the centre. The transactions table is range-partitioned by `transaction_date`, one partition per calendar month.

The reasoning is straightforward: every analytics query is time-bounded. `WHERE transaction_date >= NOW() - INTERVAL '7 days'` shouldn't touch 100K rows — it should touch one partition. With monthly partitioning, the planner prunes to O(1) partitions regardless of total table size.

I seeded the database with 10,000 users, 1,000 products, and 100,000 transactions distributed across the last 180 days. I also built two materialized views — `daily_metrics` and `user_metrics` — that pre-aggregate the raw rows. The `daily_metrics` view collapses 100K rows into 182 rows. For "show me the last 30 days of revenue," the planner reads 30 rows instead of tens of thousands.

**The first real bug hit here.** My schema defined partitions only for January through June 2024. My seed data, generated in early 2026, produces dates from September 2025 to March 2026. PostgreSQL returned:

```
ERROR: no partition of relation "transactions" found for row
```

The fix: add monthly partitions through 2026, plus a `DEFAULT` catch-all:

```sql
CREATE TABLE transactions_default
    PARTITION OF transactions DEFAULT;
```

The DEFAULT partition is a safety net. In production you'd automate future partition creation — a simple Airflow DAG that runs on the first of each month. Never rely solely on DEFAULT in a high-write system; it becomes a monolithic catch-all that defeats the purpose of partitioning.

---

## Phase 2: Kafka Streaming Pipeline

The event producer simulates a realistic user session funnel:

```
page_view (100%) → product_click (70%) → add_to_cart (40%) → purchase (20%)
```

Not every session converts. The producer probabilistically drops users at each stage, generating realistic abandonment data. Events go to `user_events`; completed purchases go to `transactions`. Both topics have 4 partitions.

The consumer is a Python process that deserialises JSON events and writes to PostgreSQL via a connection pool.

**Bug #5 surfaced here — and it took me embarrassingly long to find.** The real-time dashboard was showing zeros for last-hour KPI queries. The query looked correct:

```sql
WHERE transaction_date >= NOW() - INTERVAL '1 hour'
```

The consumer was writing data. The rows existed. But the dashboard showed nothing.

The problem: the consumer was writing timestamps using Python's `datetime.now()`, which returns local time. PostgreSQL's `NOW()` returns UTC. On my machine (UTC-5), that's a 5-hour gap — every transaction appeared to be 5 hours in the future relative to the query window.

The fix is one line:

```python
# Wrong
"transaction_date": datetime.fromisoformat(event["timestamp"])

# Right
"transaction_date": datetime.now(timezone.utc).replace(tzinfo=None)
```

`replace(tzinfo=None)` strips the timezone object before passing to psycopg2, avoiding a separate class of offset-naive vs offset-aware comparison errors. The stored value is UTC, `NOW()` is UTC, the query works.

**Lesson:** Store timestamps in UTC. Always. Without exception. The cost of timezone bugs in production dwarfs the cost of being disciplined about this from day one.

---

## Phase 3: Airflow Orchestration

Four DAGs:

1. **`hourly_refresh_dag`** — runs every hour, rebuilds `daily_metrics` and `user_metrics` concurrently with `REFRESH MATERIALIZED VIEW CONCURRENTLY` so reads aren't blocked
2. **`daily_analytics_dag`** — runs at 02:00, computes RFM scores and churn probability per user, updates segment labels in the database
3. **`data_quality_dag`** — runs at 01:30, executes 7 checks in parallel (null rates, orphaned foreign keys, revenue anomalies, stale view detection) then fans back into a single summary task using `TriggerRule.ALL_DONE`
4. **`model_retraining_dag`** — runs weekly (Sunday 03:00), retrains churn model, gates promotion behind AUC ≥ 0.55, writes to a `model_registry` table

The quality checks pattern is worth pausing on. Seven tasks fan out in parallel, then converge at a `summarize_quality` task that runs regardless of upstream success or failure (`TriggerRule.ALL_DONE`). This makes quality failures visible in the Airflow UI immediately without blocking the summary. You get a complete picture of what passed and what failed in a single DAG run.

**Bug #1 hit in the Docker Compose setup.** I was creating the Airflow admin user in a multi-line YAML bash command:

```yaml
# This silently breaks
command: >
  bash -c "airflow users create
    --username admin
    --password admin
    --role Admin
    --email admin@example.com"
```

YAML's `>` fold operator joins lines with spaces, which *looks* correct — but the shell was interpreting each `--flag` as a separate command. The user was never created. The fix: one line.

```yaml
command: >-
  bash -c "airflow users create --username admin --password admin --role Admin --email admin@example.com || true &&
    airflow webserver & airflow scheduler"
```

Boring fix. Genuinely infuriating to diagnose when the container starts, prints no obvious error, and simply has no admin user.

---

## Phase 4: FastAPI + Redis

The API has 22 endpoints across five routers: dashboard KPIs, products, customers, recommendations, and health checks.

**Tiered TTL caching:**

```python
cache_ttl_short  = 60     # live KPIs — 1 minute
cache_ttl_medium = 300    # product performance — 5 minutes
cache_ttl_long   = 3600   # historical trends — 1 hour
```

TTL tiers reflect freshness requirements. Last-hour revenue needs to be current; a 30-day cohort trend from last month can be an hour stale without anyone noticing.

**`ThreadedConnectionPool`** avoids the ~50ms overhead of establishing a new PostgreSQL connection on every request:

```python
pool = ThreadedConnectionPool(minconn=2, maxconn=10, **db_config)
```

Under modest concurrency this is the single highest-ROI optimisation available to a Python database API. The 50ms per-connection overhead compounds quickly at scale.

The churn model is a scikit-learn logistic regression loaded from disk at startup. But the model only exists after the first weekly retraining run — so on day one, the API uses a heuristic: `recency_days > 90` → churned. Simple, interpretable, always available. When the model file appears, it takes over automatically. This pattern — heuristic baseline + model override — is underused in production ML systems.

---

## Phase 5: Streamlit Dashboard

Five pages: real-time KPIs, product analytics, customer segmentation, churn leaderboard, and a deep-dive explorer for individual customers or products. Everything uses a Plotly dark theme. The app auto-refreshes every 60 seconds via `streamlit-autorefresh`.

Two bugs, both obvious in hindsight.

**Bug #6: Jinja2 not found.** Pandas `.style.applymap()` requires Jinja2 as a dependency. It was installed system-wide but not in the active virtual environment. Rather than fight it, I removed the pandas styling and used plain DataFrames. Sometimes the right fix is deletion.

**Bug #7: Streamlit import paths.** Streamlit adds the entry script's directory to `sys.path`. So when running `streamlit run dashboards/streamlit_app.py`, Python looks for modules relative to `dashboards/` — not the project root. Every import needed to drop the package prefix:

```python
# Fails — Python looks for dashboards/dashboards/components/style.py
from dashboards.components.style import SEGMENT_COLORS

# Works — Python finds dashboards/components/style.py
from components.style import SEGMENT_COLORS
```

One-word fix per import, across seven files. The error message (`ModuleNotFoundError: No module named 'dashboards'`) points you in the wrong direction if you don't know this behaviour.

---

## The Spark Detour

I added an optional PySpark Structured Streaming layer for windowed aggregations directly on the Kafka stream. **Bug #3** appeared immediately:

```
AnalysisException: Distinct aggregations are not supported on streaming DataFrames
```

Spark Structured Streaming can't maintain exact distinct counts across distributed streaming windows — the bookkeeping would require coordination that breaks the stateless execution model. The fix is `approx_count_distinct()`, which uses HyperLogLog at roughly 2% relative error:

```python
# Fails in streaming context
.agg(countDistinct("user_id"))

# Works — HyperLogLog, ~2% relative error
.agg(approx_count_distinct("user_id"))
```

For analytics cardinality estimates, 2% error is completely acceptable.

**Bug #4** was a JDBC timezone rejection. PostgreSQL inside Docker refused the JVM's local timezone `"America/Indianapolis"` (not in the container's timezone database). Fix: pass the timezone explicitly through the JDBC connection properties:

```python
jdbc_properties = {
    "user": "postgres",
    "password": "postgres",
    "driver": "org.postgresql.Driver",
    "options": "-c TimeZone=UTC",   # PostgreSQL startup parameter
}
df.write.jdbc(url=jdbc_url, table="realtime_metrics",
              mode="append", properties=jdbc_properties)
```

Note: this requires using `.write.jdbc()` with a properties dict, not the fluent `.format("jdbc").option(...)` API — the latter doesn't pass arbitrary keys as JDBC connection properties.

---

## Performance Numbers (With Honest Caveats)

Real query times, measured with `EXPLAIN ANALYZE` on a local Docker environment running on WSL2:

| Query | Execution Time | Why |
|---|---|---|
| Real-time KPIs (last 1 hour) | 0.24 ms | Partition pruning — 26 of 27 partitions eliminated |
| Single user RFM lookup | 0.075 ms | Unique btree index on materialized view |
| 30-day daily KPIs | 0.077 ms | 182-row materialized view scan |
| Top 10 products join (24h) | 2.6 ms | Bitmap index + hash join |
| Churn leaderboard (2,945 users) | 7 ms | Full segment filter + sort |
| Redis cache read | 0.22 ms | In-memory, same host |

The 0.24ms KPI query is the one I'm most satisfied with. The partition pruner eliminates 26 of 27 monthly partitions at plan time. At 100K rows this isn't dramatic — at 100M rows it's the difference between fast and broken.

**The caveats I'd put in any production design doc:**

These are local, warm-cache, single-connection numbers. In production, add:
- 1–50ms network latency between app and database
- 5–20x slowdown under concurrent load with a fixed connection pool
- Cold cache penalty on the first request after a restart

Design your p99 budgets around 50–100ms, not sub-millisecond benchmarks. The architectural decisions that produce sub-millisecond times locally — partitioning, materialized views, indexed lookups, Redis — are exactly the decisions that keep queries fast at real load. The numbers just look different.

---

## The ML Section I Wish More Posts Were Honest About

The churn model achieves AUC 1.0 on the synthetic dataset.

That sounds impressive. It's a red flag.

The churn label is `recency_days > 90`. One of the model's input features is `recency_days`. The model is learning to replicate a threshold of its own input — that's direct data leakage. On real behavioural data with genuinely noisy features, you'd see AUC somewhere in the 0.65–0.80 range for a well-tuned logistic regression on this problem.

The RFM clustering silhouette score is -0.25. A negative silhouette means points are, on average, closer to a neighbouring cluster than their own. That's because synthetic random transaction data has no real behavioural structure — uniform noise. The binning algorithm finds nothing meaningful because there is nothing meaningful to find.

**None of this undermines the platform's value, because the value is the pipeline:**

- Weekly model training triggered by Airflow
- AUC evaluation gate that blocks promotion if performance falls below 0.55
- Model registry with versioned metrics stored in PostgreSQL
- Heuristic fallback so the API never returns an error due to a missing model file
- `classification_report` and `cross_val_score` baked into the evaluation step

When you replace the synthetic data with real user behaviour, the ML components work correctly. The infrastructure is production-appropriate. The metrics on fake data are not — and that distinction is worth making explicitly.

---

## Lessons Learned

**1. UTC everywhere, from the first line of code.** Timezone bugs are invisible until they surface at 2am in production. `datetime.now(timezone.utc)` costs two extra words. Write them.

**2. Partition coverage must precede data insertion.** PostgreSQL will not create partitions on the fly. If your seed script or event producer can generate dates outside your defined range, add a DEFAULT partition before you run anything.

**3. Multi-line YAML bash commands are a footgun.** If a shell command has flags, put it on one line or write a proper entrypoint script. YAML folding looks correct and behaves incorrectly.

**4. The heuristic baseline is not a concession — it's architecture.** A system that degrades gracefully to a simple rule on day one is more valuable than a system that is unavailable until the first model finishes training.

**5. Materialized views are chronically underused.** A 182-row view refreshed hourly outperforms a 100K-row scan every time it runs. The refresh cost is paid once per hour; the read savings are paid on every query.

**6. Benchmark honestly and state your environment.** Local warm-cache latency numbers are useful for comparing approaches, not for quoting in design documents. Always state what "fast" means and what it doesn't.

---

## Conclusion

This project took longer than expected, broke in ways I didn't anticipate, and produced ML metrics that look suspicious for good reason. I learned more from the bugs than from the parts that worked the first time.

The architecture — partitioned storage, materialized views, streaming ingestion, orchestrated refresh, cached API, live dashboard — is a reasonable template for a real analytics platform. Each component does one job. The data flow is unidirectional. The failure modes are localised.

If you're building something similar: get your schema right before you write your first event, get your timestamps right before you build your first dashboard, and don't ship ML endpoints without a heuristic fallback.

The full project covers schema design, all four Airflow DAGs, the Kafka producer and consumer, FastAPI routers, Redis caching strategy, and the complete Streamlit dashboard. The bugs described here are real and reproducible. Every fix is in the codebase.

---

*If this was useful, the best thing you can do is build something with it and write about what broke for you.*
