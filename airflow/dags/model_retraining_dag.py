"""
DAG 4: Model Retraining Pipeline
Schedule: 3:00 AM every Sunday
Retrains RFM segmentation thresholds and churn logistic regression model.
Promotes to model_registry, then triggers daily_analytics_dag.
"""

from datetime import datetime, timedelta
import json
import logging

from airflow import DAG
from airflow.exceptions import AirflowException
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.postgres.operators.postgres import PostgresOperator

log = logging.getLogger(__name__)

POSTGRES_CONN_ID = "ecommerce_postgres"
MIN_TRAINING_ROWS = 1000


# ---------------------------------------------------------------------------
# Task functions
# ---------------------------------------------------------------------------

def extract_training_data(**context):
    import pandas as pd

    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    conn = hook.get_conn()

    df = pd.read_sql("""
        SELECT user_id, recency_days, frequency, monetary, avg_order_value
        FROM user_metrics
        WHERE frequency > 0
    """, conn)
    conn.close()

    log.info("Extracted training data: shape=%s", df.shape)
    context["ti"].xcom_push(key="training_shape", value=list(df.shape))

    # Store as records (XCom-serialisable)
    context["ti"].xcom_push(key="training_data", value=df.to_dict(orient="records"))


def validate_training_data(**context):
    records = context["ti"].xcom_pull(task_ids="extract_training_data", key="training_data")
    n = len(records) if records else 0
    log.info("Training data rows: %d", n)
    if n < MIN_TRAINING_ROWS:
        raise AirflowException(
            f"Insufficient training data: {n} rows (minimum {MIN_TRAINING_ROWS})"
        )


def train_rfm_model(**context):
    import json
    import numpy as np
    import pandas as pd
    from sklearn.preprocessing import KBinsDiscretizer

    records = context["ti"].xcom_pull(task_ids="extract_training_data", key="training_data")
    df = pd.DataFrame(records)

    features = ["recency_days", "frequency", "monetary"]
    X = df[features].values.astype(float)

    est = KBinsDiscretizer(n_bins=5, encode="ordinal", strategy="quantile")
    est.fit(X)

    breakpoints = {}
    for i, feat in enumerate(features):
        edges = est.bin_edges_[i].tolist()
        breakpoints[feat] = [round(e, 4) for e in edges]

    with open("/tmp/rfm_breakpoints.json", "w") as f:
        json.dump(breakpoints, f, indent=2)

    log.info("RFM breakpoints: %s", breakpoints)
    context["ti"].xcom_push(key="rfm_breakpoints", value=breakpoints)


def train_churn_model(**context):
    import joblib
    import numpy as np
    import pandas as pd
    from xgboost import XGBClassifier

    records = context["ti"].xcom_pull(task_ids="extract_training_data", key="training_data")
    df = pd.DataFrame(records)

    # Forward-looking label: snapshot = max date − 30 days.
    # The DAG's extract_training_data already pulled user_metrics which reflects
    # the current state; for the label we approximate using recency relative to
    # a 30-day window.  Full forward-looking logic lives in train_model.py for
    # offline training; here we use a proxy that is consistent with it.
    LABEL_WINDOW = 30
    y = (df["recency_days"] > LABEL_WINDOW).astype(int).values

    feature_names = ["recency_days", "frequency", "monetary", "avg_order_value"]
    X_base = df[feature_names].fillna(0).values.astype(float)

    # Derived features
    tenure   = np.maximum(df["recency_days"].values.astype(float), 1)
    velocity = df["frequency"].values.astype(float) / tenure
    ratio    = df["recency_days"].values.astype(float) / tenure

    X = np.column_stack([X_base, tenure, velocity, ratio])
    all_features = feature_names + ["tenure_days", "purchase_velocity", "recency_ratio"]

    n_pos = int(y.sum())
    n_neg = int((y == 0).sum())
    scale = n_neg / max(n_pos, 1)

    model = XGBClassifier(
        n_estimators=400,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale,
        random_state=42,
        eval_metric="auc",
        verbosity=0,
    )
    model.fit(X, y)

    # Build SHAP explainer
    try:
        import shap
        explainer = shap.TreeExplainer(model)
    except Exception:
        explainer = None

    artifact = {
        "model":         model,
        "explainer":     explainer,
        "feature_names": all_features,
        "model_name":    "XGBoost",
        "cv_auc":        None,
    }
    joblib.dump(artifact, "/tmp/churn_model.pkl")

    meta = {
        "feature_names": all_features,
        "n_train":       len(X),
        "churn_rate":    float(y.mean()),
    }
    log.info("Churn model trained: %s", meta)
    context["ti"].xcom_push(key="churn_model_meta", value=meta)


def evaluate_models(**context):
    import joblib
    import numpy as np
    import pandas as pd
    from sklearn.metrics import roc_auc_score, silhouette_score
    from sklearn.model_selection import train_test_split

    records = context["ti"].xcom_pull(task_ids="extract_training_data", key="training_data")
    df = pd.DataFrame(records)

    # --- RFM silhouette score ---
    rfm_features = ["recency_days", "frequency", "monetary"]
    X_rfm = df[rfm_features].fillna(0).values.astype(float)

    breakpoints = context["ti"].xcom_pull(task_ids="train_rfm_model", key="rfm_breakpoints")
    # Assign each user a simple composite score for silhouette
    from sklearn.preprocessing import KBinsDiscretizer
    est = KBinsDiscretizer(n_bins=5, encode="ordinal", strategy="quantile")
    labels_rfm = est.fit_transform(X_rfm).sum(axis=1).astype(int)

    sil_score = silhouette_score(X_rfm, labels_rfm, sample_size=min(3000, len(X_rfm)))
    log.info("RFM silhouette score: %.4f", sil_score)

    # --- Churn AUC ---
    model = joblib.load("/tmp/churn_model.pkl")
    feature_names = ["recency_days", "frequency", "monetary", "avg_order_value"]
    X_churn = df[feature_names].fillna(0).values.astype(float)
    y_churn = (df["recency_days"] > 90).astype(int).values

    _, X_test, _, y_test = train_test_split(X_churn, y_churn, test_size=0.2, random_state=42)
    y_prob = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_prob)
    log.info("Churn model AUC: %.4f", auc)

    metrics = {"silhouette_score": round(sil_score, 4), "churn_auc": round(auc, 4)}
    context["ti"].xcom_push(key="eval_metrics", value=metrics)

    if auc < 0.75:
        raise AirflowException(
            f"Churn model AUC {auc:.4f} is below threshold 0.75 — promotion blocked. "
            "Check data quality or retrain with more data."
        )

    log.info("Model evaluation passed: %s", metrics)


def promote_models(**context):
    ti = context["ti"]
    breakpoints = ti.xcom_pull(task_ids="train_rfm_model",  key="rfm_breakpoints")
    churn_meta  = ti.xcom_pull(task_ids="train_churn_model", key="churn_model_meta")
    eval_metrics = ti.xcom_pull(task_ids="evaluate_models",  key="eval_metrics")

    version = datetime.now().strftime("%Y-%m-%d")

    rfm_metrics  = json.dumps({"breakpoints": breakpoints,
                                "silhouette": eval_metrics.get("silhouette_score")})
    churn_metrics = json.dumps({"auc": eval_metrics.get("churn_auc"), **churn_meta})

    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    hook.run("""
        INSERT INTO model_registry (model_name, version, trained_at, metrics, is_active)
        VALUES
            ('rfm_segmentation', %(version)s, NOW(), %(rfm_metrics)s::jsonb, TRUE),
            ('churn_model',      %(version)s, NOW(), %(churn_metrics)s::jsonb, TRUE)
        ON CONFLICT (model_name, version) DO UPDATE
            SET metrics   = EXCLUDED.metrics,
                is_active = TRUE,
                trained_at = EXCLUDED.trained_at;
    """, parameters={
        "version": version,
        "rfm_metrics": rfm_metrics,
        "churn_metrics": churn_metrics,
    })

    log.info("Models promoted to registry: version=%s", version)


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------

default_args = {
    "owner": "data-science",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}

with DAG(
    dag_id="model_retraining_dag",
    description="Weekly RFM + churn model retraining with AUC gate and registry promotion",
    schedule_interval="0 3 * * 0",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["ml", "weekly", "rfm", "churn", "phase3"],
) as dag:

    t_extract = PythonOperator(
        task_id="extract_training_data",
        python_callable=extract_training_data,
    )

    t_validate = PythonOperator(
        task_id="validate_training_data",
        python_callable=validate_training_data,
    )

    t_train_rfm = PythonOperator(
        task_id="train_rfm_model",
        python_callable=train_rfm_model,
    )

    t_train_churn = PythonOperator(
        task_id="train_churn_model",
        python_callable=train_churn_model,
    )

    t_evaluate = PythonOperator(
        task_id="evaluate_models",
        python_callable=evaluate_models,
    )

    t_promote = PythonOperator(
        task_id="promote_models",
        python_callable=promote_models,
    )

    t_trigger_daily = TriggerDagRunOperator(
        task_id="trigger_rfm_update",
        trigger_dag_id="daily_analytics_dag",
        wait_for_completion=False,
    )

    # Pipeline order
    t_extract >> t_validate >> [t_train_rfm, t_train_churn] >> t_evaluate >> t_promote >> t_trigger_daily
