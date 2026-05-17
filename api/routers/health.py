import time

from fastapi import APIRouter, Depends
import psycopg2
import redis

from api.config import settings
from api.dependencies import get_db, get_redis
from api.models.schemas import DBHealth, HealthStatus, RedisHealth

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthStatus)
def health():
    return {"status": "ok", "version": settings.api_version}


@router.get("/db", response_model=DBHealth)
def health_db(conn=Depends(get_db)):
    start = time.perf_counter()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        latency_ms = (time.perf_counter() - start) * 1000
        return {"status": "ok", "latency_ms": round(latency_ms, 2)}
    except Exception as exc:
        return {"status": f"error: {exc}", "latency_ms": -1}


@router.get("/redis", response_model=RedisHealth)
def health_redis(r: redis.Redis = Depends(get_redis)):
    start = time.perf_counter()
    try:
        r.ping()
        latency_ms = (time.perf_counter() - start) * 1000
        return {"status": "ok", "latency_ms": round(latency_ms, 2)}
    except Exception as exc:
        return {"status": f"error: {exc}", "latency_ms": -1}
