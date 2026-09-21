"""Tests for schemas/catalog/inventory.py - quantity/threshold constraints."""

import pytest
from pydantic import ValidationError

from schemas.catalog.inventory import Base, LocationBase, AdjustmentCreate


class TestBaseConstraints:

    def test_rejects_negative_quantity(self):
        from uuid import uuid4
        with pytest.raises(ValidationError):
            Base(variant_id=uuid4(), location_id=uuid4(), quantity=-1)

    def test_defaults_quantity_to_zero(self):
        from uuid import uuid4
        inv = Base(variant_id=uuid4(), location_id=uuid4())
        assert inv.quantity == 0
        assert inv.low_stock_threshold == 10


class TestLocationBase:

    def test_requires_non_empty_name(self):
        with pytest.raises(ValidationError):
            LocationBase(name="")


class TestAdjustmentCreate:

    def test_requires_reason(self):
        with pytest.raises(ValidationError):
            AdjustmentCreate(quantity_change=5)
