from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    database_url: str = "sqlite:///./database.db"
    environment: str = "development"
    log_level: str = "info"
    upload_dir: Path = Path("uploads")


@lru_cache
def get_settings() -> Settings:
    return Settings()
