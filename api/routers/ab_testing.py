"""
A/B Testing router — churn discount experiment.

WHY A/B TESTING:
    The churn model tells us *who* is at risk.  But knowing a user is at risk
    does not reduce churn — an intervention does.  This endpoint assigns
    high-risk users to the "churn-discount-v1" experiment and returns whether
    to show them a 10% discount offer.  GrowthBook's SDK handles assignment
    using a deterministic FNV hash of (user_id, experiment_key), so the same
    user always lands in the same variant across requests.

WHY GROWTHBOOK SDK IN INLINE MODE:
    The SDK evaluates the experiment locally — no round-trip to the GrowthBook
    server on each API call.  Zero added latency.  The GrowthBook UI (port 3000)
    connects to Postgres as a data source and reads ab_experiment_metrics for
    statistical analysis independently of this hot path.

ENDPOINTS:
    GET /experiment/offer/{user_id}   — get variant + offer for a user
    GET /experiment/results           — current conversion counts per variant
"""

import logging
import os
import threading
import time
from typing import Any

import psycopg2
from fastapi import APIRouter, Depends, HTTPException
from growthbook import GrowthBook, Experiment

from api.dependencies import get_db

log = logging.getLogger(__name__)

router = APIRouter(prefix="/experiment", tags=["ab-testing"])

EXPERIMENT_KEY      = "churn-discount-v1"
CHURN_THRESHOLD     = 0.6
DISCOUNT_VARIANTS   = {"discount_10pct": 10, "control": 0}

# GrowthBook connection — reads from env so docker-compose injects the key
_GB_API_HOST    = os.getenv("GROWTHBOOK_API_HOST",   "http://growthbook:3100")
_GB_CLIENT_KEY  = os.getenv("GROWTHBOOK_CLIENT_KEY", "")

# Cache features for 1 hour so we don't HTTP-call GrowthBook on every request
_feature_cache: dict = {}
_cache_lock           = threading.Lock()
_cache_loaded_at: float = 0.0
_CACHE_TTL            = 3600.0


def _load_features() -> dict:
    global _feature_cache, _cache_loaded_at
    now = time.monotonic()
    with _cache_lock:
        if now - _cache_loaded_at < _CACHE_TTL and _feature_cache:
            return _feature_cache
        try:
            gb = GrowthBook(api_host=_GB_API_HOST, client_key=_GB_CLIENT_KEY)
            gb.load_features()
            _feature_cache = gb.get_features() or {}
            _cache_loaded_at = now
            log.info("GrowthBook features refreshed (%d features)", len(_feature_cache))
        except Exception as exc:
            log.warning("GrowthBook feature fetch failed (using inline experiment): %s", exc)
        return _feature_cache


def _assign_variant(user_id: int) -> tuple[str, bool]:
    """
    Use GrowthBook SDK to deterministically assign a variant.
    Fetches feature definitions from GrowthBook (cached 1h) so the UI shows
    "Connected" and can push experiment changes without an API redeploy.
    Falls back to the inline experiment definition if GrowthBook is unreachable.
    """
    features = _load_features() if _GB_CLIENT_KEY else {}
    gb = GrowthBook(
        api_host=_GB_API_HOST,
        client_key=_GB_CLIENT_KEY,
        attributes={"id": str(user_id)},
        features=features,
    )
    result = gb.run(Experiment(
        key=EXPERIMENT_KEY,
        variations=["control", "discount_10pct"],
        weights=[0.5, 0.5],
    ))
    return result.value, result.inExperiment


def _log_assignment(conn, user_id: int, variant: str) -> None:
    """Insert assignment — ON CONFLICT DO NOTHING keeps first assignment stable."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ab_assignments (user_id, experiment_key, variant)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, experiment_key) DO NOTHING
            """,
            (user_id, EXPERIMENT_KEY, variant),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/offer/{user_id}")
def get_churn_offer(user_id: int, conn=Depends(get_db)) -> dict[str, Any]:
    """
    Returns the discount offer (if any) for a user.

    - Users with churn_risk < 0.6 are not eligible.
    - Eligible users are 50/50 split: control (no offer) vs discount_10pct.
    - Assignment is sticky — same user always gets the same variant.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT churn_risk_score FROM users WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    churn_risk = float(row["churn_risk_score"] or 0.0)

    if churn_risk < CHURN_THRESHOLD:
        return {
            "user_id":       user_id,
            "churn_risk":    round(churn_risk, 4),
            "eligible":      False,
            "variant":       None,
            "show_discount": False,
            "discount_pct":  0,
        }

    variant, in_experiment = _assign_variant(user_id)

    try:
        _log_assignment(conn, user_id, variant)
    except Exception as exc:
        log.warning("Failed to log AB assignment for user %d: %s", user_id, exc)

    return {
        "user_id":       user_id,
        "churn_risk":    round(churn_risk, 4),
        "eligible":      True,
        "variant":       variant,
        "show_discount": variant == "discount_10pct",
        "discount_pct":  DISCOUNT_VARIANTS.get(variant, 0),
    }


@router.get("/results")
def get_experiment_results(conn=Depends(get_db)) -> dict[str, Any]:
    """Current assignment counts and latest conversion metrics per variant."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT variant, COUNT(*) AS assigned_users
            FROM ab_assignments
            WHERE experiment_key = %s
            GROUP BY variant
            ORDER BY variant
            """,
            (EXPERIMENT_KEY,),
        )
        assignments = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT variant, assigned_users, converted_users, conversion_rate, metric_date
            FROM ab_experiment_metrics
            WHERE experiment_key = %s
            ORDER BY metric_date DESC, variant
            LIMIT 4
            """,
            (EXPERIMENT_KEY,),
        )
        metrics = [dict(r) for r in cur.fetchall()]

    return {
        "experiment_key": EXPERIMENT_KEY,
        "assignments":    assignments,
        "latest_metrics": metrics,
    }
