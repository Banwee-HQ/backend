"""Tests for schemas/commerce/payments.py - card field constraints."""

import pytest
from pydantic import ValidationError

from schemas.commerce.payments import MethodBase, IntentCreate


class TestMethodBaseConstraints:

    def test_rejects_expiry_month_out_of_range(self):
        with pytest.raises(ValidationError):
            MethodBase(type="card", expiry_month=13)

    def test_rejects_last_four_longer_than_four_chars(self):
        with pytest.raises(ValidationError):
            MethodBase(type="card", last_four="12345")

    def test_accepts_valid_card(self):
        method = MethodBase(type="card", expiry_month=12, expiry_year=2030, last_four="4242")
        assert method.last_four == "4242"


class TestIntentCreate:

    def test_currency_is_not_client_controlled(self):
        """Intents are always in the store currency, so the request carries none."""
        assert not hasattr(IntentCreate(amount=10.0, currency="EUR"), "currency")
