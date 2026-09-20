"""Tests for core/config.py - environment validation and DB URL derivation.

Settings is a plain class (not pydantic BaseSettings), so each test builds its
own instance and overrides the attributes under test directly, rather than
touching the process-wide `settings` singleton used by the running app.
"""

from core.config import Settings


class TestValidate:

    def test_dev_environment_is_always_valid(self):
        s = Settings()
        s.ENVIRONMENT = "dev"
        s.SECRET_KEY = "dev-secret-key-change-in-production"
        result = s.validate()
        assert result["is_valid"] is True
        assert result["missing"] == []

    def test_production_with_default_secret_key_is_invalid(self):
        s = Settings()
        s.ENVIRONMENT = "production"
        s.SECRET_KEY = "dev-secret-key-change-in-production"
        result = s.validate()
        assert result["is_valid"] is False
        assert "SECRET_KEY" in result["missing"]

    def test_production_with_a_real_secret_key_is_valid(self):
        s = Settings()
        s.ENVIRONMENT = "production"
        s.SECRET_KEY = "a-real-64-character-secret-key-generated-with-secrets-token-hex"
        result = s.validate()
        assert result["is_valid"] is True
        assert result["missing"] == []


class TestDatabaseURIDerivation:

    def test_async_uri_uses_asyncpg_driver(self):
        s = Settings()
        s.DATABASE_URL = "postgresql://user:pass@localhost:5432/banwee"
        assert s.SQLALCHEMY_DATABASE_URI == "postgresql+asyncpg://user:pass@localhost:5432/banwee"

    def test_sync_uri_uses_psycopg2_driver(self):
        s = Settings()
        s.DATABASE_URL = "postgresql://user:pass@localhost:5432/banwee"
        assert s.SQLALCHEMY_DATABASE_URI_SYNC == "postgresql+psycopg2://user:pass@localhost:5432/banwee"

    def test_async_uri_does_not_double_up_if_already_asyncpg(self):
        """A URL that already names its driver must not become postgresql+asyncpg+asyncpg://."""
        s = Settings()
        s.DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/banwee"
        assert s.SQLALCHEMY_DATABASE_URI == "postgresql+asyncpg://user:pass@localhost:5432/banwee"

    def test_sync_uri_does_not_double_up_if_already_psycopg2(self):
        s = Settings()
        s.DATABASE_URL = "postgresql+psycopg2://user:pass@localhost:5432/banwee"
        assert s.SQLALCHEMY_DATABASE_URI_SYNC == "postgresql+psycopg2://user:pass@localhost:5432/banwee"
