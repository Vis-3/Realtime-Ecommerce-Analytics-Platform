import json
import logging
from typing import Generator

import psycopg2
import psycopg2.extras
import psycopg2.pool
import redis

from api.config import settings

log = logging.getLogger(__name__)

_db_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_redis_client: redis.Redis | None = None


def init_db_pool() -> None:
    global _db_pool
    if settings.database_url:
        # Neon / Render: DATABASE_URL = postgresql://user:pass@host/db?sslmode=require
        _db_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2, maxconn=10, dsn=settings.database_url
        )
    else:
        _db_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password,
        )
    log.info("PostgreSQL connection pool initialised (min=2, max=10)")


def close_db_pool() -> None:
    if _db_pool:
        _db_pool.closeall()
        log.info("PostgreSQL connection pool closed")


def init_redis() -> None:
    global _redis_client
    if settings.redis_url:
        # Upstash: REDIS_URL = rediss://default:pass@host:port  (note: rediss:// = TLS)
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    else:
        _redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
        )
    _redis_client.ping()
    log.info("Redis connection established")


def close_redis() -> None:
    if _redis_client:
        _redis_client.close()
        log.info("Redis connection closed")


# ---------------------------------------------------------------------------
# FastAPI dependency injectors
# ---------------------------------------------------------------------------

def get_db() -> Generator:
    conn = _db_pool.getconn()
    try:
        yield conn
    finally:
        _db_pool.putconn(conn)


def get_redis() -> redis.Redis:
    return _redis_client


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def cache_get(redis_client: redis.Redis, key: str):
    try:
        raw = redis_client.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:
        log.warning("Redis GET failed for key=%s: %s", key, exc)
        return None


def cache_set(redis_client: redis.Redis, key: str, value, ttl: int) -> None:
    try:
        redis_client.setex(key, ttl, json.dumps(value, default=str))
    except Exception as exc:
        log.warning("Redis SET failed for key=%s: %s", key, exc)
