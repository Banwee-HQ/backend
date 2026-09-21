"""Tests for schemas/accounts/auth.py."""

import pytest
from pydantic import ValidationError

from schemas.accounts.auth import Login, Refresh, ForgotPassword


class TestLogin:

    def test_requires_valid_email(self):
        with pytest.raises(ValidationError):
            Login(email="not-an-email", password="secret")

    def test_accepts_valid_credentials(self):
        login = Login(email="a@example.com", password="secret")
        assert login.password == "secret"


class TestRefresh:

    def test_requires_refresh_token(self):
        with pytest.raises(ValidationError):
            Refresh()


class TestForgotPassword:

    def test_requires_valid_email(self):
        with pytest.raises(ValidationError):
            ForgotPassword(email="nope")
