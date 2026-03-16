"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Top-level application settings sourced from .env / environment."""

    DATABASE_URL: str
    SECRET_KEY: str
    DEBUG: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
