"""Tests for core/config.py - environment validation and DB URL derivation.

Settings is a plain class (not pydantic BaseSettings), so each test builds its
own instance and overrides the attributes under test directly, rather than
touching the process-wide `settings` singleton used by the running app.
"""

import importlib
from pathlib import Path

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


class TestEnvFileSelectionAtImportTime:
    """The module picks which .env file to load once, at import time, based on
    ENVIRONMENT and which files exist on disk. Reload the module under controlled
    conditions to exercise the branches the normal test-time import (ENVIRONMENT=
    "test", real .env.dev present) never takes. Nothing else imports `core.config`
    as a module object (everyone does `from core.config import settings`), so
    reloading it doesn't retroactively change any other module's already-bound
    `settings` reference - it only rebinds the name inside core.config itself,
    which is restored to the real environment afterward.
    """

    def test_production_environment_selects_env_prod_file(self, monkeypatch, mocker):
        import core.config as core_config

        monkeypatch.setenv("ENVIRONMENT", "production")
        mock_load_dotenv = mocker.patch("dotenv.load_dotenv")
        mocker.patch.object(Path, "exists", autospec=True, return_value=True)
        try:
            importlib.reload(core_config)
            assert mock_load_dotenv.call_args[0][0].name == ".env.prod"
        finally:
            monkeypatch.setenv("ENVIRONMENT", "test")
            importlib.reload(core_config)

    def test_falls_back_to_bare_env_file_when_environment_specific_one_is_missing(self, monkeypatch, mocker):
        import core.config as core_config

        monkeypatch.setenv("ENVIRONMENT", "dev")
        mock_load_dotenv = mocker.patch("dotenv.load_dotenv")
        # Neither .env.dev nor .env.prod exist, but the bare .env fallback does.
        mocker.patch.object(Path, "exists", autospec=True, side_effect=lambda self: self.name == ".env")
        try:
            importlib.reload(core_config)
            mock_load_dotenv.assert_called_once()
            assert mock_load_dotenv.call_args[0][0].name == ".env"
        finally:
            monkeypatch.setenv("ENVIRONMENT", "test")
            importlib.reload(core_config)

    def test_loads_nothing_when_no_env_file_exists_at_all(self, monkeypatch, mocker):
        import core.config as core_config

        monkeypatch.setenv("ENVIRONMENT", "dev")
        mock_load_dotenv = mocker.patch("dotenv.load_dotenv")
        mocker.patch.object(Path, "exists", autospec=True, return_value=False)
        try:
            importlib.reload(core_config)
            mock_load_dotenv.assert_not_called()
        finally:
            monkeypatch.setenv("ENVIRONMENT", "test")
            importlib.reload(core_config)
