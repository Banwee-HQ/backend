"""Configuration - PostgreSQL only."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment-specific .env file
env = os.getenv("ENVIRONMENT", "dev").lower()
base_dir = Path(__file__).resolve().parents[1]  # backend directory

if env in ("production", "prod"):
    env_file = base_dir / ".env.prod"
else:
    env_file = base_dir / ".env.dev"

if env_file.exists():
    load_dotenv(env_file)
elif (base_dir / ".env").exists():
    load_dotenv(base_dir / ".env")


class Settings:
    """Minimal settings with SQLite/PostgreSQL support."""

    # Core
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "dev")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

    # Frontend
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    BACKEND_CORS_ORIGINS: list = ["*"] if os.getenv("ENVIRONMENT", "dev") == "dev" else \
        [os.getenv("FRONTEND_URL", "http://localhost:5173")]

    # Database - PostgreSQL only
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/banwee")
    # Connection pooling
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))

    SEARCH_PATH = "accounts,catalog,commerce,admin,system,public"

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """Async PostgreSQL URI."""
        url = self.DATABASE_URL
        if url.startswith("postgresql"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            url = url.replace("postgresql+asyncpg+asyncpg://", "postgresql+asyncpg://", 1)
        return url

    @property
    def SQLALCHEMY_DATABASE_URI_SYNC(self) -> str:
        """Sync PostgreSQL URI (for migrations)."""
        url = self.DATABASE_URL
        if url.startswith("postgresql"):
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
            url = url.replace("postgresql+psycopg2+psycopg2://", "postgresql+psycopg2://", 1)
        return url

    # Auth
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    ALGORITHM: str = "HS256"

    # Payments (Stripe)
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    # Email (optional)
    BREVO_API_KEY: str = os.getenv("BREVO_API_KEY", "")
    BREVO_FROM_EMAIL: str = os.getenv("BREVO_FROM_EMAIL", "Banwee <noreply@banwee.com>")

    # OAuth - Google
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")

    # OAuth - Facebook
    FACEBOOK_APP_ID: str = os.getenv("FACEBOOK_APP_ID", "")
    FACEBOOK_APP_SECRET: str = os.getenv("FACEBOOK_APP_SECRET", "")

    def validate(self) -> dict:
        """Check required settings."""
        missing = []
        if self.ENVIRONMENT == "production":
            if self.SECRET_KEY == "dev-secret-key-change-in-production":
                missing.append("SECRET_KEY")
        return {"is_valid": len(missing) == 0, "missing": missing}


settings = Settings()
