"""Tests for schemas/commerce/cart.py - dietary tag normalization and quantity constraints."""

import pytest
from pydantic import ValidationError

from schemas.commerce.cart import Add
from schemas.commerce.cart import EnhancedProductVariantResponse


class TestAdd:

    def test_defaults_quantity_to_one(self):
        from uuid import uuid4
        item = Add(variant_id=uuid4())
        assert item.quantity == 1

    def test_rejects_zero_quantity(self):
        from uuid import uuid4
        with pytest.raises(ValidationError):
            Add(variant_id=uuid4(), quantity=0)


class TestEnhancedProductVariantResponseDietaryTags:

    def test_normalizes_list_input(self):
        from uuid import uuid4
        from datetime import datetime
        variant = EnhancedProductVariantResponse(
            id=uuid4(), product_id=uuid4(), sku="SKU1", name="Small", base_price=9.99, sale_price=None,
            current_price=9.99, discount_percentage=0, stock=5, attributes=None,
            is_active=True, created_at=datetime.now(), product_dietary_tags=["vegan"],
        )
        assert variant.product_dietary_tags == {"vegan": True}