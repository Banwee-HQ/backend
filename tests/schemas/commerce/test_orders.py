"""Tests for schemas/commerce/orders.py."""

import pytest
from pydantic import ValidationError

from schemas.commerce.orders import Checkout, ShipOrder


class TestCheckout:

    def test_requires_shipping_and_payment_ids(self):
        with pytest.raises(ValidationError):
            Checkout()

    def test_defaults_currency_and_country(self):
        from uuid import uuid4
        checkout = Checkout(shipping_address_id=uuid4(), shipping_method_id=uuid4(), payment_method_id=uuid4())
        assert checkout.currency == "USD"
        assert checkout.country_code == "US"


class TestShipOrder:

    def test_requires_tracking_number_and_carrier(self):
        with pytest.raises(ValidationError):
            ShipOrder(tracking_number="123")
