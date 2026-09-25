"""Tests for schemas/commerce/shipping.py - price/estimated_days constraints."""

import pytest
from pydantic import ValidationError

from schemas.commerce.shipping import MethodBase, Calculate


class TestMethodBaseConstraints:

    def test_rejects_negative_price(self):
        with pytest.raises(ValidationError):
            MethodBase(name="Standard", price=-1, estimated_days=3)

    def test_rejects_zero_estimated_days(self):
        with pytest.raises(ValidationError):
            MethodBase(name="Standard", price=5, estimated_days=0)

    def test_accepts_valid_method(self):
        method = MethodBase(name="Standard", price=5, estimated_days=3)
        assert method.is_active is True


class TestCalculate:

    def test_method_is_optional(self):
        """No method means "cheapest active method" for the delivery estimate."""
        assert Calculate().shipping_method_id is None
