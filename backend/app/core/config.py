from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FairLens API"
    app_env: str = "development"

    # Database — defaults to file-based SQLite for dev, override with Postgres in production
    database_url: str = "sqlite+pysqlite:///./fairlens.db"

    # Storage
    upload_dir: Path = Field(default=Path("../uploads"))
    reports_dir: Path = Field(default=Path("../reports"))

    # Gemini AI
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"

    # Upload limits
    max_upload_size_mb: int = 50

    # CORS
    cors_origins: list[str] = ["http://localhost:5173"]

    # Auth — set FAIRLENS_AUTH_DISABLED=false in production
    jwt_secret_key: str = "CHANGE-ME-in-production"
    auth_disabled: bool = True

    # Celery (if not set, uses FastAPI BackgroundTasks)
    celery_broker_url: str | None = None

    # Rate limits
    rate_limit_default: str = "100/minute"
    rate_limit_probe: str = "10/minute"
    rate_limit_webhook: str = "1000/minute"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="FAIRLENS_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
