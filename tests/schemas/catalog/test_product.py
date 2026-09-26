"""Tests for schemas/catalog/product.py - normalize_dietary_tags and variant schemas."""

import pytest
from pydantic import ValidationError

from schemas.catalog.product import normalize_dietary_tags, VariantCreate, VariantUpdate, VariantResponse, Create


class TestNormalizeDietaryTags:

    def test_none_becomes_empty_dict(self):
        assert normalize_dietary_tags(None) == {}

    def test_dict_passes_through(self):
        assert normalize_dietary_tags({"vegan": True}) == {"vegan": True}

    def test_list_becomes_dict_with_true_values(self):
        assert normalize_dietary_tags(["vegan", "gluten_free"]) == {"vegan": True, "gluten_free": True}

    def test_other_types_become_empty_dict(self):
        assert normalize_dietary_tags("vegan") == {}


class TestVariantCreateDietaryTags:

    def test_normalizes_list_input(self):
        variant = VariantCreate(name="Small", base_price=9.99, sale_price=9.99, dietary_tags=["vegan"])
        assert variant.dietary_tags == {"vegan": True}

    def test_normalizes_none_input(self):
        variant = VariantCreate(name="Small", base_price=9.99, sale_price=9.99, dietary_tags=None)
        assert variant.dietary_tags == {}


class TestVariantUpdateDietaryTags:

    def test_normalizes_list_input(self):
        variant = VariantUpdate(dietary_tags=["gluten_free"])
        assert variant.dietary_tags == {"gluten_free": True}


class TestVariantResponseDietaryTags:

    def test_normalizes_list_input(self):
        from uuid import uuid4
        from datetime import datetime
        variant = VariantResponse(
            id=uuid4(), product_id=uuid4(), sku="SKU1", name="Small", base_price=9.99, sale_price=None,
            current_price=9.99, discount_percentage=0, stock=5, attributes=None, dietary_tags=["nut_free"],
            is_active=True, created_at=datetime.now(),
        )
        assert variant.dietary_tags == {"nut_free": True}


class TestCreate:

    def test_sale_price_is_optional(self):
        assert Create(name="Coffee", slug="coffee", category_id="00000000-0000-0000-0000-000000000000").sale_price is None
