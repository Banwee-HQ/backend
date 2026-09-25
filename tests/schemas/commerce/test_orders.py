"""Tests for schemas/commerce/orders.py."""

import pytest
from pydantic import ValidationError

from schemas.commerce.orders import Checkout
from schemas.commerce.orders import ShipOrder


class TestCheckout:

    def test_requires_shipping_and_payment_ids(self):
        with pytest.raises(ValidationError):
            Checkout()

    def test_currency_is_not_client_controlled(self):
        """Prices are charged in the store currency, so checkout takes no currency/country input."""
        from uuid import uuid4
        checkout = Checkout(shipping_address_id=uuid4(), shipping_method_id=uuid4(), payment_method_id=uuid4(), currency="EUR")
        assert not hasattr(checkout, "currency")
        assert checkout.discount_code is None


class TestShipOrder:

    def test_requires_tracking_number_and_carrier(self):
        with pytest.raises(ValidationError):
            ShipOrder(tracking_number="123")