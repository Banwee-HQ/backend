"""Tests for schemas/commerce/cart.py - dietary tag normalization and quantity constraints."""

import pytest
from pydantic import ValidationError

from schemas.commerce.cart import Add


class TestAdd:

    def test_defaults_quantity_to_one(self):
        from uuid import uuid4
        item = Add(variant_id=uuid4())
        assert item.quantity == 1

    def test_rejects_zero_quantity(self):
        from uuid import uuid4
        with pytest.raises(ValidationError):
            Add(variant_id=uuid4(), quantity=0)

