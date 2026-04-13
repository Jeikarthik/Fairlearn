from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FairLens API"
    app_env: str = "development"
    database_url: str = "sqlite+pysqlite:///:memory:"
    upload_dir: Path = Field(default=Path("../uploads"))
    reports_dir: Path = Field(default=Path("../reports"))
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"
    max_upload_size_mb: int = 50
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
