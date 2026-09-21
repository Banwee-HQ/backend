"""Tests for schemas/commerce/subscriptions.py."""

import pytest
from pydantic import ValidationError

from schemas.commerce.subscriptions import Create, UpdateQuantity, CostCalculation


class TestCreate:

    def test_defaults_name_and_currency(self):
        sub = Create()
        assert sub.name == "My Subscription"
        assert sub.currency == "CAD"


class TestUpdateQuantity:

    def test_rejects_zero_quantity(self):
        with pytest.raises(ValidationError):
            UpdateQuantity(variant_id="v1", quantity=0)

    def test_accepts_positive_quantity(self):
        update = UpdateQuantity(variant_id="v1", quantity=2)
        assert update.quantity == 2


class TestCostCalculation:

    def test_requires_variant_ids(self):
        with pytest.raises(ValidationError):
            CostCalculation()
