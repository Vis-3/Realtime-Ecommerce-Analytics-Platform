"""
Churn Prediction — Model Training
===================================
Trains XGBoost, LightGBM, and GradientBoosting on enriched RFM features.
Saves the best model (by ROC-AUC) together with a SHAP TreeExplainer so
the API can explain individual predictions.

WHY FORWARD-LOOKING LABEL:
    Defining churn as recency_days > 90 and then using recency_days as a
    feature is circular — the model trivially learns the threshold and reports
    near-perfect AUC on noise.  Instead we split time at a snapshot point:
      • Features  = everything up to snapshot_date
      • Label     = did the user make NO purchase in the 30 days after snapshot?
    The model must therefore learn BEHAVIOURAL patterns, not re-derive the label.

WHY XGBOOST / LIGHTGBM:
    The At-Risk persona has HIGH historical frequency AND HIGH recency — a
    non-linear interaction that logistic regression cannot capture.  Tree
    ensembles split on feature combinations and naturally learn "was active,
    now gone", which is the hardest and most valuable churn signal.

WHY SHAP:
    A churn score of 0.87 is not actionable.  SHAP shows exactly which
    features pushed this user's score up (e.g. "recency_ratio contributed
    +0.32") so the business knows what to act on.

Usage:
    python train_model.py [--output models/churn_model.pkl]
"""

import argparse
import logging
import os
import sys
from typing import Optional

import joblib
import numpy as np
import psycopg2
import psycopg2.extras
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_score

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MIN_AUC          = 0.75
MIN_TRAIN_ROWS   = 200
LABEL_WINDOW_DAYS = 30   # days after snapshot that define the label

# The full feature set.  Order must match exactly — this list is saved in the
# artifact so the API always uses the same ordering the model was trained on.
FEATURE_NAMES = [
    "recency_days",      # days since last purchase at snapshot
    "frequency",         # total orders up to snapshot
    "monetary",          # total spend up to snapshot
    "avg_order_value",   # monetary / frequency
    "tenure_days",       # days from first to last purchase (customer age)
    "purchase_velocity", # orders per day  (frequency / tenure_days)
    "recency_ratio",     # recency / tenure — is this silence unusual for them?
]


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_connection():
    if url := os.getenv("DATABASE_URL"):
        return psycopg2.connect(dsn=url)
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "ecommerce"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    )


# ---------------------------------------------------------------------------
# Feature extraction — forward-looking label
# ---------------------------------------------------------------------------

def fetch_training_data(conn) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Returns (X, y, user_ids).

    Snapshot date = max(transaction_date) − LABEL_WINDOW_DAYS.
    Features are computed on transactions BEFORE the snapshot.
    Label = 1 (churned) if the user made NO purchase in the LABEL_WINDOW_DAYS
            days after the snapshot.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(f"""
        WITH snapshot AS (
            SELECT MAX(transaction_date)::date - {LABEL_WINDOW_DAYS} AS snap_date
            FROM transactions
        ),
        pre AS (
            -- Features: only transactions up to snapshot
            SELECT
                t.user_id,
                s.snap_date,
                (s.snap_date - MAX(t.transaction_date)::date)   AS recency_days,
                COUNT(DISTINCT t.transaction_id)                 AS frequency,
                SUM(t.total_amount)                              AS monetary,
                AVG(t.total_amount)                              AS avg_order_value,
                GREATEST(
                    s.snap_date - MIN(t.transaction_date)::date, 1
                )                                                AS tenure_days
            FROM transactions t
            CROSS JOIN snapshot s
            WHERE t.transaction_date::date <= s.snap_date
            GROUP BY t.user_id, s.snap_date
            HAVING COUNT(DISTINCT t.transaction_id) >= 1
        ),
        post AS (
            -- Label: any purchase after snapshot within the window?
            SELECT DISTINCT t.user_id
            FROM transactions t
            CROSS JOIN snapshot s
            WHERE t.transaction_date::date >  s.snap_date
              AND t.transaction_date::date <= s.snap_date + {LABEL_WINDOW_DAYS}
        )
        SELECT
            pre.user_id,
            pre.recency_days,
            pre.frequency,
            pre.monetary,
            pre.avg_order_value,
            pre.tenure_days,
            pre.frequency::float / pre.tenure_days          AS purchase_velocity,
            pre.recency_days::float / pre.tenure_days       AS recency_ratio,
            CASE WHEN post.user_id IS NULL THEN 1 ELSE 0 END AS churned
        FROM pre
        LEFT JOIN post ON post.user_id = pre.user_id
    """)
    rows = cur.fetchall()
    cur.close()

    user_ids = np.array([r["user_id"] for r in rows])
    X = np.array([[
        float(r["recency_days"]    or 0),
        float(r["frequency"]       or 0),
        float(r["monetary"]        or 0),
        float(r["avg_order_value"] or 0),
        float(r["tenure_days"]     or 1),
        float(r["purchase_velocity"] or 0),
        float(r["recency_ratio"]   or 0),
    ] for r in rows])
    y = np.array([int(r["churned"]) for r in rows])
    return X, y, user_ids


# ---------------------------------------------------------------------------
# Model candidates
# ---------------------------------------------------------------------------

def build_candidates(class_ratio: float) -> dict:
    """
    class_ratio = n_negative / n_positive — used for XGBoost class weighting.
    """
    try:
        from xgboost import XGBClassifier
        xgb = XGBClassifier(
            n_estimators=400,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=class_ratio,
            random_state=42,
            eval_metric="auc",
            verbosity=0,
        )
    except ImportError:
        xgb = None
        log.warning("xgboost not installed — skipping XGBClassifier")

    try:
        from lightgbm import LGBMClassifier
        lgbm = LGBMClassifier(
            n_estimators=400,
            max_depth=5,
            learning_rate=0.05,
            num_leaves=31,
            subsample=0.8,
            class_weight="balanced",
            random_state=42,
            verbosity=-1,
        )
    except ImportError:
        lgbm = None
        log.warning("lightgbm not installed — skipping LGBMClassifier")

    gbm = GradientBoostingClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        random_state=42,
    )

    candidates = {"GradientBoosting": gbm}
    if xgb is not None:
        candidates["XGBoost"] = xgb
    if lgbm is not None:
        candidates["LightGBM"] = lgbm
    return candidates


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate(name: str, model, X: np.ndarray, y: np.ndarray) -> float:
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    aucs = cross_val_score(model, X, y, cv=cv, scoring="roc_auc", n_jobs=-1)
    log.info("%-18s  AUC = %.4f ± %.4f", name, aucs.mean(), aucs.std())
    return float(aucs.mean())


# ---------------------------------------------------------------------------
# SHAP explainer
# ---------------------------------------------------------------------------

def compute_shap_values_native(model, X: np.ndarray) -> Optional[np.ndarray]:
    """
    Compute SHAP values using XGBoost's built-in C++ implementation.
    No shap package required — XGBoost ships the same algorithm natively.
    predict(pred_contribs=True) returns shape (n, n_features+1);
    the last column is the bias term which we drop.
    Returns None for non-XGBoost models.
    """
    try:
        import xgboost as xgb
        dmatrix = xgb.DMatrix(X)
        contribs = model.get_booster().predict(dmatrix, pred_contribs=True)
        shap_values = contribs[:, :-1]   # drop bias term
        log.info("SHAP values computed via XGBoost native (shape=%s)", shap_values.shape)
        return shap_values
    except Exception as exc:
        log.warning("Native SHAP computation failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def train_and_save(output_path: str) -> None:
    log.info("Connecting to database …")
    conn = get_connection()

    log.info("Fetching training data (forward-looking label, window=%d days) …",
             LABEL_WINDOW_DAYS)
    X, y, user_ids = fetch_training_data(conn)
    conn.close()

    n_pos = int(y.sum())
    n_neg = int((y == 0).sum())
    log.info("Dataset: %d users | churned=%d (%.1f%%) | retained=%d",
             len(y), n_pos, 100 * n_pos / len(y), n_neg)

    if len(y) < MIN_TRAIN_ROWS:
        log.error("Not enough data — need ≥ %d users, got %d.", MIN_TRAIN_ROWS, len(y))
        sys.exit(1)

    class_ratio = n_neg / max(n_pos, 1)
    candidates  = build_candidates(class_ratio)

    log.info("Evaluating %d models with 5-fold CV …", len(candidates))
    results = {name: evaluate(name, m, X, y) for name, m in candidates.items()}

    best_name = max(results, key=results.get)
    best_auc  = results[best_name]

    # Prefer XGBoost when it is within 0.5% AUC of the leader.
    # XGBoost supports native SHAP (pred_contribs=True); sklearn GBM does not.
    # A 0.005 AUC difference is well within noise — explainability is worth it.
    if best_name != "XGBoost" and "XGBoost" in results:
        gap = best_auc - results["XGBoost"]
        if gap <= 0.005:
            log.info(
                "Preferring XGBoost (AUC=%.4f) over %s (AUC=%.4f) "
                "— gap=%.4f within 0.5%% tolerance; XGBoost provides native SHAP.",
                results["XGBoost"], best_name, best_auc, gap,
            )
            best_name = "XGBoost"
            best_auc  = results["XGBoost"]

    log.info("Selected model: %s  AUC=%.4f", best_name, best_auc)

    if best_auc < MIN_AUC:
        log.error(
            "Best AUC %.4f is below threshold %.2f — refusing to save model. "
            "Check data quality or add more training samples.",
            best_auc, MIN_AUC
        )
        sys.exit(1)

    log.info("Fitting %s on full dataset …", best_name)
    best_model = candidates[best_name]
    best_model.fit(X, y)

    # Full-dataset metrics
    y_prob = best_model.predict_proba(X)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)
    log.info("Train AUC: %.4f", roc_auc_score(y, y_prob))
    log.info("\n%s", classification_report(y, y_pred, target_names=["Retained", "Churned"]))

    # Compute and cache SHAP values on training set for the explainer lookup
    shap_sample = compute_shap_values_native(best_model, X[:500])

    artifact = {
        "model":         best_model,
        "feature_names": FEATURE_NAMES,
        "model_name":    best_name,
        "cv_auc":        best_auc,
        # Store a sample of SHAP values for reference; per-prediction SHAP
        # is computed at inference time via the same native XGBoost call.
        "shap_sample":   shap_sample,
    }

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    joblib.dump(artifact, output_path)
    log.info("Artifact saved to %s  (model=%s, native SHAP=%s)",
             output_path, best_name, "yes" if shap_sample is not None else "no")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="models/churn_model.pkl",
                        help="Output path for the model artifact")
    args = parser.parse_args()
    train_and_save(args.output)
