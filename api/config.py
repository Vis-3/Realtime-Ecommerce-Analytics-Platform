from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL — set DATABASE_URL (Neon/Render) OR individual fields (local)
    database_url: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ecommerce"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"

    # Redis — set REDIS_URL (Upstash) OR individual fields (local)
    redis_url: str = ""
    redis_host: str = "localhost"
    redis_port: int = 6379

    # Cache TTLs (seconds)
    cache_ttl_short: int = 60        # live metrics
    cache_ttl_medium: int = 300      # per-user data
    cache_ttl_long: int = 3600       # aggregations, segments

    # ML
    model_path: str = "/tmp"

    # App
    api_version: str = "1.0.0"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
