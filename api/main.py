import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.dependencies import (
    close_db_pool,
    close_redis,
    init_db_pool,
    init_redis,
)
from api.models.ml_models import load_churn_model
from api.routers import ab_testing, customers, dashboard, health, products, recommendations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (startup + shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting up E-Commerce Analytics API v%s", settings.api_version)
    init_db_pool()
    init_redis()
    load_churn_model(settings.model_path)
    log.info("Startup complete — all connections ready")
    yield
    log.info("Shutting down...")
    close_db_pool()
    close_redis()
    log.info("Shutdown complete")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="E-Commerce Analytics API",
    description=(
        "Real-time analytics, RFM segmentation, churn scoring, "
        "and product recommendations."
    ),
    version=settings.api_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    log.info(
        "%s %s → %s  (%.1f ms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(health.router)
app.include_router(customers.router)
app.include_router(recommendations.router)
app.include_router(dashboard.router)
app.include_router(products.router)
app.include_router(ab_testing.router)


@app.get("/", include_in_schema=False)
def root():
    return {
        "name":    "E-Commerce Analytics API",
        "version": settings.api_version,
        "docs":    "/docs",
    }
