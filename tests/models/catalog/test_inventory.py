"""Tests for models/catalog/inventories.py - Inventory.atomic_update_stock and stock_status.

atomic_update_stock is what every add-to-cart/checkout/refund stock change goes
through, so its validation (never go negative) and bookkeeping (version bump,
timestamps) need direct coverage independent of the API layer.
"""

import pytest
from datetime import datetime, timezone

from models.catalog.inventories import Inventory
from core.exceptions import APIException


class FakeSession:
    """Stand-in for AsyncSession - atomic_update_stock only calls db.add()."""
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


def make_inventory(quantity_available=10, low_stock_threshold=5, version=0) -> Inventory:
    inv = Inventory()
    inv.id = "inventory-id"
    inv.variant_id = "variant-id"
    inv.quantity_available = quantity_available
    inv.low_stock_threshold = low_stock_threshold
    inv.version = version
    inv.last_restocked_at = None
    inv.last_sold_at = None
    return inv


class TestStockStatus:

    def test_zero_is_out_of_stock(self):
        assert make_inventory(quantity_available=0).stock_status == "out_of_stock"

    def test_negative_is_out_of_stock(self):
        assert make_inventory(quantity_available=-1).stock_status == "out_of_stock"

    def test_at_or_below_threshold_is_low_stock(self):
        assert make_inventory(quantity_available=5, low_stock_threshold=5).stock_status == "low_stock"

    def test_above_threshold_is_in_stock(self):
        assert make_inventory(quantity_available=6, low_stock_threshold=5).stock_status == "in_stock"


class TestAtomicUpdateStock:

    async def test_increasing_stock_updates_quantity_available(self):
        inv = make_inventory(quantity_available=10)
        await inv.atomic_update_stock(FakeSession(), quantity_change=5, reason="restock")
        assert inv.quantity_available == 15

    async def test_decreasing_stock_updates_quantity_available(self):
        inv = make_inventory(quantity_available=10)
        await inv.atomic_update_stock(FakeSession(), quantity_change=-3, reason="sale")
        assert inv.quantity_available == 7

    async def test_decrease_below_zero_is_rejected(self):
        inv = make_inventory(quantity_available=5)
        with pytest.raises(APIException) as exc_info:
            await inv.atomic_update_stock(FakeSession(), quantity_change=-10, reason="sale")
        assert exc_info.value.status_code == 400
        # Rejected changes must not partially apply.
        assert inv.quantity_available == 5

    async def test_decrease_to_exactly_zero_is_allowed(self):
        inv = make_inventory(quantity_available=5)
        await inv.atomic_update_stock(FakeSession(), quantity_change=-5, reason="sale")
        assert inv.quantity_available == 0

    async def test_version_increments_on_every_successful_update(self):
        inv = make_inventory(quantity_available=10, version=3)
        await inv.atomic_update_stock(FakeSession(), quantity_change=1, reason="restock")
        assert inv.version == 4

    async def test_version_does_not_increment_on_rejected_update(self):
        inv = make_inventory(quantity_available=5, version=3)
        with pytest.raises(APIException):
            await inv.atomic_update_stock(FakeSession(), quantity_change=-100, reason="sale")
        assert inv.version == 3

    async def test_decrease_sets_last_sold_at(self):
        inv = make_inventory(quantity_available=10)
        await inv.atomic_update_stock(FakeSession(), quantity_change=-1, reason="sale")
        assert inv.last_sold_at is not None
        assert inv.last_restocked_at is None

    async def test_increase_sets_last_restocked_at(self):
        inv = make_inventory(quantity_available=10)
        await inv.atomic_update_stock(FakeSession(), quantity_change=1, reason="restock")
        assert inv.last_restocked_at is not None
        assert inv.last_sold_at is None

    async def test_creates_an_audit_adjustment_record(self):
        session = FakeSession()
        inv = make_inventory(quantity_available=10)
        adjustment = await inv.atomic_update_stock(session, quantity_change=-2, reason="damaged")
        assert session.added == [adjustment]
        assert adjustment.quantity_change == -2
        assert adjustment.reason == "damaged"

    async def test_notes_default_to_a_generated_summary_when_not_given(self):
        inv = make_inventory(quantity_available=10)
        adjustment = await inv.atomic_update_stock(FakeSession(), quantity_change=5, reason="restock")
        assert "10" in adjustment.notes and "15" in adjustment.notes
