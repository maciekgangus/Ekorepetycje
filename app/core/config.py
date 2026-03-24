"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Top-level application settings sourced from .env / environment."""

    DATABASE_URL: str
    SECRET_KEY: str
    DEBUG: bool = False

    # ── Email (Resend) ────────────────────────────────────────────────────────
    # Leave RESEND_API_KEY empty to fall back to logging (local dev / CI).
    RESEND_API_KEY: str = ""
    # "From" address must be on a domain you have verified in Resend.
    # Use "onboarding@resend.dev" for initial testing before domain verification.
    RESEND_FROM_EMAIL: str = "Ekorepetycje <onboarding@resend.dev>"
    # Where contact-form submissions are delivered.
    RESEND_TO_EMAIL: str = "kontakt@ekorepetycje.pl"

    # ── Cloudflare Turnstile (CAPTCHA) ────────────────────────────────────────
    # Default values are Cloudflare's official test keys — always pass locally.
    # Replace with real keys from https://dash.cloudflare.com/ before going live.
    TURNSTILE_SITE_KEY: str = "1x00000000000000000000AA"
    TURNSTILE_SECRET_KEY: str = "1x0000000000000000000000000000000AA"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_file_encoding="utf-8")


settings = Settings()
