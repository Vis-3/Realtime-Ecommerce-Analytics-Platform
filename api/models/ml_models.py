"""
ML model loading and inference for the churn prediction API.

The artifact saved by train_model.py is a dict:
  {
    "model":         fitted XGBoost / LightGBM / GBM,
    "explainer":     shap.TreeExplainer  (or None),
    "feature_names": list[str],
    "model_name":    str,
    "cv_auc":        float,
  }

Backward compat: if the loaded object is a raw sklearn Pipeline (old format),
it is wrapped transparently so predict_churn still works.
"""

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

# Must match the order used in train_model.py
FEATURE_NAMES = [
    "recency_days",
    "frequency",
    "monetary",
    "avg_order_value",
    "tenure_days",
    "purchase_velocity",
    "recency_ratio",
]

FEATURE_LABELS = {
    "recency_days":      "days since last purchase",
    "frequency":         "total orders",
    "monetary":          "total spend",
    "avg_order_value":   "average order value",
    "tenure_days":       "customer tenure (days)",
    "purchase_velocity": "purchase rate (orders/day)",
    "recency_ratio":     "silence relative to tenure",
}

_artifact: Optional[dict] = None
_loaded   = False


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_churn_model(model_path: str = "models") -> Optional[dict]:
    """
    Load the churn artifact from disk.  Returns the artifact dict, or None.
    Called once at API startup; result is cached in module state.
    """
    global _artifact, _loaded
    if _loaded:
        return _artifact

    try:
        import joblib

        path = os.path.join(model_path, "churn_model.pkl")
        if not os.path.exists(path):
            log.warning("Churn model not found at %s", path)
            _loaded = True
            return None

        obj = joblib.load(path)

        # New format: dict with model + explainer
        if isinstance(obj, dict) and "model" in obj:
            _artifact = obj
        else:
            # Old format: raw Pipeline — wrap for backward compat
            log.info("Old-format model detected — wrapping for compatibility")
            _artifact = {
                "model":         obj,
                "explainer":     None,
                "feature_names": ["recency_days", "frequency", "monetary", "avg_order_value"],
                "model_name":    "legacy",
                "cv_auc":        None,
            }

        name = _artifact.get("model_name", "unknown")
        auc  = _artifact.get("cv_auc")
        log.info("Churn model loaded: %s  CV-AUC=%s  native-SHAP=yes",
                 name,
                 f"{auc:.4f}" if auc else "n/a")

    except Exception as exc:
        log.warning("Failed to load churn model: %s", exc)

    _loaded = True
    return _artifact


# ---------------------------------------------------------------------------
# Feature preparation
# ---------------------------------------------------------------------------

def _prepare_features(features: dict, feature_names: list[str]) -> list[float]:
    """
    Build the feature vector in the correct order.
    Derives tenure_days, purchase_velocity, and recency_ratio from base
    RFM values when not explicitly supplied, so the API router does not
    need to compute them separately.
    """
    recency   = float(features.get("recency_days",    365))
    frequency = float(features.get("frequency",       1))
    monetary  = float(features.get("monetary",        0))
    aov       = float(features.get("avg_order_value", 0))

    # Tenure: prefer explicit value, else estimate from first/last purchase dates
    if "tenure_days" in features:
        tenure = max(float(features["tenure_days"]), 1)
    elif "first_purchase_date" in features and "last_purchase_date" in features:
        from datetime import date
        fp = features["first_purchase_date"]
        lp = features["last_purchase_date"]
        if hasattr(fp, "date"):
            fp = fp.date()
        if hasattr(lp, "date"):
            lp = lp.date()
        tenure = max((lp - fp).days, 1)
    else:
        # Rough estimate: assume avg inter-purchase of 30 days
        tenure = max(frequency * 30, recency, 1)

    purchase_velocity = frequency / tenure
    recency_ratio     = recency   / tenure

    lookup = {
        "recency_days":      recency,
        "frequency":         frequency,
        "monetary":          monetary,
        "avg_order_value":   aov,
        "tenure_days":       tenure,
        "purchase_velocity": purchase_velocity,
        "recency_ratio":     recency_ratio,
    }
    return [lookup.get(f, 0.0) for f in feature_names]


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------

def predict_churn(artifact: Optional[dict], features: dict) -> tuple[float, str]:
    """
    Returns (probability, label) where label ∈ {Low, Medium, High}.
    Falls back to a simple heuristic if the model is unavailable.
    """
    if artifact is not None:
        try:
            import numpy as np
            fname = artifact.get("feature_names", FEATURE_NAMES)
            X     = np.array([_prepare_features(features, fname)])
            prob  = float(artifact["model"].predict_proba(X)[0][1])
        except Exception as exc:
            log.warning("Model inference failed (%s) — using heuristic", exc)
            prob = _heuristic_churn(features)
    else:
        prob = _heuristic_churn(features)

    label = "High" if prob >= 0.7 else "Medium" if prob >= 0.4 else "Low"
    return round(prob, 4), label


# ---------------------------------------------------------------------------
# Explainability
# ---------------------------------------------------------------------------

def get_risk_factors(artifact: Optional[dict], features: dict) -> list[str]:
    """
    Return top-2 human-readable risk factors.

    Uses SHAP values when the explainer is available — these reflect the
    actual contribution of each feature to the prediction, not just the
    feature value.  Falls back to rule-based factors otherwise.
    """
    if artifact is not None and artifact.get("model") is not None:
        try:
            import numpy as np
            import xgboost as xgb

            fname = artifact.get("feature_names", FEATURE_NAMES)
            X     = np.array([_prepare_features(features, fname)])

            # Use XGBoost's native SHAP — same algorithm, no extra package.
            # pred_contribs returns (n_samples, n_features + 1); last col is bias.
            dmatrix   = xgb.DMatrix(X)
            contribs  = artifact["model"].get_booster().predict(dmatrix, pred_contribs=True)
            sv        = contribs[0, :-1]   # drop bias term

            abs_sv  = np.abs(sv)
            top_idx = abs_sv.argsort()[-2:][::-1]

            return [
                _format_shap_factor(fname[i], features, sv[i])
                for i in top_idx
            ]
        except Exception as exc:
            log.warning("Native SHAP explanation failed (%s) — using rules", exc)

    return _rule_based_factors(features)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _heuristic_churn(features: dict) -> float:
    """Simple rule-based fallback — not ML, but better than nothing."""
    recency   = features.get("recency_days", 365)
    frequency = features.get("frequency", 1)
    r_score = min(1.0, recency / 365)
    f_score = 1.0 - min(1.0, frequency / 20)
    return round(r_score * 0.6 + f_score * 0.4, 4)


def _format_shap_factor(feature: str, features: dict, shap_val: float) -> str:
    label     = FEATURE_LABELS.get(feature, feature)
    val       = features.get(feature, 0)
    direction = "High" if shap_val > 0 else "Low"

    if feature in ("recency_days", "tenure_days"):
        val_str = f"{int(val)} days"
    elif feature in ("frequency",):
        val_str = f"{int(val)} orders"
    elif feature in ("purchase_velocity",):
        val_str = f"{val:.3f}/day"
    elif feature in ("recency_ratio",):
        val_str = f"{val:.2f}x"
    else:
        val_str = f"${val:.0f}"

    return f"{direction} {label} ({val_str})"


def _rule_based_factors(features: dict) -> list[str]:
    factors = []
    recency   = features.get("recency_days", 0)
    frequency = features.get("frequency", 0)
    monetary  = features.get("monetary", 0)

    if recency > 90:
        factors.append(f"High recency — {recency} days since last purchase")
    if frequency < 3:
        factors.append(f"Low frequency — only {frequency} orders")
    if monetary < 100:
        factors.append(f"Low total spend — ${monetary:.0f}")

    return factors[:2] if factors else ["Insufficient purchase history"]
