"""Simplified application configuration loader.

Behavior:
- Loads either `backend/.env.dev` or `backend/.env.prod` depending on `ENVIRONMENT`.
- Exposes a single `settings` object with common configuration values.
- Constructs `POSTGRES_DB_URL` from DB_* components if a full URL is not provided.

This file intentionally keeps validation and complexity minimal. For stricter
validation add checks where needed or use Pydantic models in a separate module.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)


def _choose_env_file() -> Path:
    env = os.getenv("ENVIRONMENT", "dev").lower()
    base = Path(__file__).resolve().parents[2]
    if env in ("production", "prod"):
        return base / "backend" / ".env.prod"
    return base / "backend" / ".env.dev"


def _load_env() -> None:
    """Load the chosen environment file if it exists."""
    env_path = _choose_env_file()
    if env_path.exists():
        load_dotenv(dotenv_path=str(env_path))
        logger.info("Loaded environment from %s", env_path)
    else:
        logger.info("No env file found at %s; relying on process environment", env_path)


def parse_cors(value: str | None) -> List[str]:
    """Parse CORS origins from a comma-separated string.

    If no value is provided, return environment-specific defaults:
    - dev: local origins
    - prod: production origins
    """
    if not value:
        env = os.getenv("ENVIRONMENT", "dev").lower()
        if env in ("production", "prod"):
            return [
                "https://www.banwee.com",
                "https://banwee.com",
            ]
        # default to development origins
        return ["http://localhost:5173", "http://127.0.0.1:5173","http://localhost:3000","http://127.0.0.1:3000"]

    # Accept JSON-like array strings or comma-separated lists
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        # remove brackets and optional quotes
        items = [i.strip().strip('"').strip("'") for i in value[1:-1].split(",")]
        return [v for v in items if v]

    return [v.strip() for v in value.split(",") if v.strip()]


class Settings:
    """Simple container for application settings."""

    def __init__(self) -> None:
        _load_env()

        self.ENVIRONMENT: str = os.getenv("ENVIRONMENT", "dev")
        self.DOMAIN: str = os.getenv("DOMAIN", "localhost")

        self.FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
        self.BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")
        self.BACKEND_CORS_ORIGINS: List[str] = parse_cors(os.getenv("BACKEND_CORS_ORIGINS"))

        # Database
        self.POSTGRES_DB_URL: str = os.getenv("POSTGRES_DB_URL", "")
        self.DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "20"))
        self.DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "30"))
        self.DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
        self.DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "3600"))

        # Security & tokens
        self.SECRET_KEY: str = os.getenv("SECRET_KEY", "")
        self.ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
        self.ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
        self.REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

        # Stripe
        self.STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
        self.STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")

        # Email (Brevo)
        self.BREVO_API_KEY: str = os.getenv("BREVO_API_KEY", "")
        self.BREVO_FROM_EMAIL: str = os.getenv("BREVO_FROM_EMAIL", "Banwee <noreply@banwee.com>")

        # Misc
        self.ADMIN_USER_ID: str = os.getenv("ADMIN_USER_ID", "")
        self.NOTIFICATION_CLEANUP_DAYS: int = int(os.getenv("NOTIFICATION_CLEANUP_DAYS", "30"))
        self.NOTIFICATION_CLEANUP_INTERVAL_SECONDS: int = int(os.getenv("NOTIFICATION_CLEANUP_INTERVAL_SECONDS", "86400"))

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """Return an async-compatible DB URI (adds +asyncpg if missing)."""
        if not self.POSTGRES_DB_URL:
            raise ValueError("POSTGRES_DB_URL is not configured")
        uri = self.POSTGRES_DB_URL
        if "+asyncpg" not in uri and "+psycopg2" not in uri:
            uri = uri.replace("postgresql://", "postgresql+asyncpg://")
        return uri

    @property
    def SQLALCHEMY_DATABASE_URI_SYNC(self) -> str:
        """Return a sync DB URI (psycopg2) for sync operations."""
        if not self.POSTGRES_DB_URL:
            raise ValueError("POSTGRES_DB_URL is not configured")
        uri = self.POSTGRES_DB_URL
        if "+psycopg2" not in uri:
            if "+asyncpg" in uri:
                uri = uri.replace("+asyncpg", "+psycopg2")
            else:
                uri = uri.replace("postgresql://", "postgresql+psycopg2://")
        return uri


def validate_startup_environment() -> dict:
    """Simple validator that returns missing required variables.

    Returns a dict: { 'is_valid': bool, 'missing': [names] }
    """
    required = ["SECRET_KEY", "POSTGRES_DB_URL"]
    missing = [k for k in required if not os.getenv(k) and not getattr(settings, k, None)]
    return {"is_valid": len(missing) == 0, "missing": missing}


# Create and export a singleton settings object used throughout the app
settings = Settings()
