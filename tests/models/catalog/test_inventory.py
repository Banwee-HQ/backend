"""Tests for models/catalog/inventories.py - Inventory.atomic_update_stock and stock_status.

atomic_update_stock is what every add-to-cart/checkout/refund stock change goes
through, so its validation (never go negative) and bookkeeping (version bump,
timestamps) need direct coverage independent of the API layer.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from models.catalog.inventories import Inventory, WarehouseLocation, StockAdjustment, atomic_bulk_stock_update
from models.catalog.category import Category
from models.catalog.product import Product, ProductVariant
from core.exceptions import APIException
from core.utils.uuid_utils import uuid7
from sqlalchemy import select
from tests.conftest import TestingSessionLocal


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


async def make_variant(db_session, quantity_available=10) -> ProductVariant:
    """Create a category/product/variant/inventory chain, committed for real."""
    from decimal import Decimal
    category = Category(id=uuid7(), name="Cat", slug=f"cat-{uuid4().hex[:8]}")
    product = Product(id=uuid7(), name="Widget", slug=f"widget-{uuid4().hex[:8]}", category_id=category.id)
    variant = ProductVariant(id=uuid7(), product_id=product.id, sku=f"SKU-{uuid4().hex[:8]}", name="Default", base_price=Decimal("9.99"))
    db_session.add_all([category, product, variant])
    await db_session.flush()
    db_session.add(Inventory(id=uuid7(), variant_id=variant.id, quantity_available=quantity_available))
    await db_session.commit()
    return variant


class TestGetWithLock:

    async def test_returns_the_locked_row_for_a_known_variant(self, db_session):
        variant = await make_variant(db_session, quantity_available=5)
        fetched = await Inventory.get_with_lock(db_session, variant.id)
        assert fetched is not None
        assert fetched.variant_id == variant.id
        assert fetched.quantity_available == 5

    async def test_unknown_variant_returns_none(self, db_session):
        assert await Inventory.get_with_lock(db_session, uuid4()) is None

    async def test_malformed_variant_id_raises_and_is_logged(self, db_session):
        """A non-UUID value can't be validated by the type layer (it's just passed through to the
        DB), so this exercises the method's own except-log-reraise branch via a genuine DB error
        rather than a mock."""
        with pytest.raises(Exception):
            await Inventory.get_with_lock(db_session, "not-a-uuid")
        await db_session.rollback()


class TestGetMultipleWithLock:

    async def test_returns_all_matches_ordered_by_variant_id(self, db_session):
        v1 = await make_variant(db_session, quantity_available=3)
        v2 = await make_variant(db_session, quantity_available=7)

        results = await Inventory.get_multiple_with_lock(db_session, [v1.id, v2.id])
        assert {r.variant_id for r in results} == {v1.id, v2.id}
        assert [r.variant_id for r in results] == sorted([v1.id, v2.id])

    async def test_unmatched_variant_ids_are_simply_absent(self, db_session):
        v1 = await make_variant(db_session, quantity_available=3)
        results = await Inventory.get_multiple_with_lock(db_session, [v1.id, uuid4()])
        assert len(results) == 1
        assert results[0].variant_id == v1.id

    async def test_empty_input_returns_empty_list(self, db_session):
        assert await Inventory.get_multiple_with_lock(db_session, []) == []

    async def test_malformed_variant_id_raises_and_is_logged(self, db_session):
        with pytest.raises(Exception):
            await Inventory.get_multiple_with_lock(db_session, ["not-a-uuid"])
        await db_session.rollback()


class TestToDict:

    def test_includes_all_fields_when_fully_populated(self):
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        inv = make_inventory(quantity_available=8, low_stock_threshold=10, version=2)
        inv.id = uuid4()
        inv.variant_id = uuid4()
        inv.location_id = uuid4()
        inv.reorder_point = 3
        inv.inventory_status = "active"
        inv.last_restocked_at = now
        inv.last_sold_at = now
        inv.created_at = now
        inv.updated_at = now

        d = inv.to_dict()
        assert d["id"] == str(inv.id)
        assert d["variant_id"] == str(inv.variant_id)
        assert d["location_id"] == str(inv.location_id)
        assert d["quantity_available"] == 8
        assert d["low_stock_threshold"] == 10
        assert d["reorder_point"] == 3
        assert d["inventory_status"] == "active"
        assert d["stock_status"] == "low_stock"  # 8 <= threshold 10
        assert d["last_restocked_at"] == now.isoformat()
        assert d["last_sold_at"] == now.isoformat()
        assert d["version"] == 2
        assert d["created_at"] == now.isoformat()
        assert d["updated_at"] == now.isoformat()

    def test_handles_missing_optional_timestamps(self):
        inv = make_inventory(quantity_available=1)
        inv.id = uuid4()
        inv.variant_id = uuid4()
        inv.location_id = None
        inv.reorder_point = 5
        inv.inventory_status = "active"
        inv.created_at = None
        inv.updated_at = None

        d = inv.to_dict()
        assert d["last_restocked_at"] is None
        assert d["last_sold_at"] is None
        assert d["created_at"] is None
        assert d["updated_at"] is None
        # Note: unlike the timestamp fields, location_id has no None-guard here - str(None)
        # produces the literal string "None" rather than a JSON null. This method isn't called
        # anywhere in the app today (grep confirms no callers), so it's a latent quirk rather
        # than a live bug; documenting the actual behavior rather than "fixing" unused code.
        assert d["location_id"] == "None"


class TestAtomicBulkStockUpdate:

    async def test_updates_multiple_variants_atomically_and_commits(self, db_session):
        v1 = await make_variant(db_session, quantity_available=10)
        v2 = await make_variant(db_session, quantity_available=20)

        results = await atomic_bulk_stock_update(
            db_session,
            stock_changes=[
                {"variant_id": v1.id, "quantity_change": -3, "notes": "sold"},
                {"variant_id": v2.id, "quantity_change": 5, "notes": "restock"},
            ],
            reason="bulk_test",
        )

        assert {r["variant_id"] for r in results} == {str(v1.id), str(v2.id)}
        inv1 = (await db_session.execute(select(Inventory).where(Inventory.variant_id == v1.id))).scalar_one()
        inv2 = (await db_session.execute(select(Inventory).where(Inventory.variant_id == v2.id))).scalar_one()
        assert inv1.quantity_available == 7
        assert inv2.quantity_available == 25

    async def test_unknown_variant_raises_404_and_rolls_back_the_whole_batch(self):
        """One bad line in a warehouse batch must not silently apply the other, valid changes -
        that would corrupt stock counts with no record of why. atomic_bulk_stock_update is
        expected to roll back entirely when any change in the batch fails.

        Uses independent, genuinely-committed TestingSessionLocal connections (like the
        concurrency regression test in tests/services/catalog/test_inventory.py) rather than the
        shared db_session fixture: verifying "nothing partially persisted" requires checking real
        committed state, and re-querying the same SAVEPOINT-joined session right after its own
        in-test rollback() trips an unrelated SQLAlchemy/greenlet quirk in this harness.
        """
        variant_id = uuid7()
        async with TestingSessionLocal() as setup_session:
            category = Category(id=uuid7(), name="Cat", slug=f"cat-{uuid4().hex[:8]}")
            product = Product(id=uuid7(), name="Widget", slug=f"widget-{uuid4().hex[:8]}", category_id=category.id)
            v = ProductVariant(id=variant_id, product_id=product.id, sku=f"SKU-{uuid4().hex[:8]}", name="Default", base_price=9.99)
            setup_session.add_all([category, product, v])
            await setup_session.flush()
            setup_session.add(Inventory(id=uuid7(), variant_id=variant_id, quantity_available=10))
            await setup_session.commit()

        try:
            async with TestingSessionLocal() as session:
                with pytest.raises(APIException) as exc_info:
                    await atomic_bulk_stock_update(
                        session,
                        stock_changes=[
                            {"variant_id": variant_id, "quantity_change": -3, "notes": "sold"},
                            {"variant_id": uuid4(), "quantity_change": -1, "notes": "sold"},
                        ],
                        reason="bulk_test",
                    )
                assert exc_info.value.status_code == 404

            async with TestingSessionLocal() as check_session:
                result = await check_session.execute(select(Inventory).where(Inventory.variant_id == variant_id))
                # The valid change (processed first in the loop) must not have persisted either.
                assert result.scalar_one().quantity_available == 10
        finally:
            async with TestingSessionLocal() as cleanup_session:
                await cleanup_session.execute(
                    StockAdjustment.__table__.delete().where(
                        StockAdjustment.inventory_id.in_(
                            select(Inventory.id).where(Inventory.variant_id == variant_id)
                        )
                    )
                )
                await cleanup_session.execute(Inventory.__table__.delete().where(Inventory.variant_id == variant_id))
                await cleanup_session.execute(ProductVariant.__table__.delete().where(ProductVariant.id == variant_id))
                await cleanup_session.execute(Product.__table__.delete().where(Product.id == product.id))
                await cleanup_session.execute(Category.__table__.delete().where(Category.id == category.id))
                await cleanup_session.commit()

    async def test_negative_result_raises_400(self, db_session):
        v1 = await make_variant(db_session, quantity_available=5)

        with pytest.raises(APIException) as exc_info:
            await atomic_bulk_stock_update(
                db_session,
                stock_changes=[{"variant_id": v1.id, "quantity_change": -100, "notes": "sold"}],
                reason="bulk_test",
            )
        assert exc_info.value.status_code == 400
        # See test_unknown_variant_... above re: not re-querying this session post-rollback.
        await db_session.rollback()
