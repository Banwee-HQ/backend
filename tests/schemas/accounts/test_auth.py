"""Tests for schemas/accounts/auth.py."""

import pytest
from uuid import uuid4
from pydantic import ValidationError

from schemas.accounts.auth import Login, UserCreate, Refresh, ForgotPassword


class TestLogin:

    def test_requires_valid_email(self):
        with pytest.raises(ValidationError):
            Login(email="not-an-email", password="secret")

    def test_accepts_valid_credentials(self):
        login = Login(email="a@example.com", password="secret")
        assert login.password == "secret"

    def test_variant_id_defaults_to_none(self):
        login = Login(email="a@example.com", password="Secret123")
        assert login.variant_id is None
        assert login.quantity == 1

    def test_accepts_pending_cart_item(self):
        variant_id = uuid4()
        login = Login(email="a@example.com", password="Secret123", variant_id=variant_id, quantity=2)
        assert login.variant_id == variant_id
        assert login.quantity == 2


class TestUserCreate:

    def test_variant_id_defaults_to_none(self):
        user = UserCreate(email="a@example.com", password="Secret123")
        assert user.variant_id is None
        assert user.quantity == 1

    def test_accepts_pending_cart_item(self):
        variant_id = uuid4()
        user = UserCreate(email="a@example.com", password="Secret123", variant_id=variant_id, quantity=3)
        assert user.variant_id == variant_id
        assert user.quantity == 3


class TestRefresh:

    def test_requires_refresh_token(self):
        with pytest.raises(ValidationError):
            Refresh()


class TestForgotPassword:

    def test_requires_valid_email(self):
        with pytest.raises(ValidationError):
            ForgotPassword(email="nope")


class TestPasswordStrength:
    """Login stays unvalidated (existing passwords must still sign in); password-setting schemas enforce the rule."""

    def test_login_accepts_any_password(self):
        assert Login(email="a@example.com", password="x").password == "x"

    @pytest.mark.parametrize("weak", ["short1", "lettersonly", "12345678"])
    def test_user_create_rejects_weak(self, weak):
        with pytest.raises(ValidationError):
            UserCreate(email="a@example.com", password=weak)
