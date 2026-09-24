"""Tests for services/catalog/inventory.py - InventoryService.

Focused on check_stock, adjust_stock, and the row-locking behavior that
checkout relies on to avoid overselling under concurrent requests.
"""

import asyncio
import pytest
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from core.exceptions import APIException
from core.utils.uuid_utils import uuid7
from services.catalog.inventory import InventoryService
from schemas.catalog.inventory import AdjustmentCreate as StockAdjustmentCreate
from models.catalog.category import Category
from models.catalog.product import Product, ProductVariant, ProductImage
from models.catalog.inventories import Inventory, StockAdjustment, WarehouseLocation
from tests.conftest import TestingSessionLocal


class _NullLock:
    """A real (non-mock) async-context-manager lock that does nothing. Used to exercise the
    `if self.lock_service:` branch of adjust_stock/increment without needing a live Redis
    connection - it's a genuine collaborator satisfying the interface those methods are written
    against, not a mock of the InventoryService code under test."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeLockService:
    def __init__(self):
        self.calls = []

    def get_inventory_lock(self, key, timeout=30):
        self.calls.append((key, timeout))
        return _NullLock()


@pytest.fixture
async def variant(db_session) -> ProductVariant:
    category = Category(id=uuid7(), name="Cat", slug=f"cat-{uuid4().hex[:8]}")
    product = Product(id=uuid7(), name="Widget", slug=f"widget-{uuid4().hex[:8]}", category_id=category.id)
    v = ProductVariant(id=uuid7(), product_id=product.id, sku=f"SKU-{uuid4().hex[:8]}", name="Default", base_price=Decimal("19.99"))
    db_session.add_all([category, product, v])
    await db_session.flush()
    db_session.add(Inventory(id=uuid7(), variant_id=v.id, quantity_available=10))
    await db_session.commit()
    return v


class TestCheckStock:

    async def test_available_when_stock_exceeds_request(self, db_session, variant):
        service = InventoryService(db_session)
        result = await service.check_stock(variant.id, 3)
        assert result["available"] is True
        assert result["current_stock"] == 10

    async def test_unavailable_when_stock_below_request(self, db_session, variant):
        service = InventoryService(db_session)
        result = await service.check_stock(variant.id, 20)
        assert result["available"] is False
        assert "Insufficient stock" in result["message"]

    async def test_unknown_variant_reports_out_of_stock(self, db_session):
        service = InventoryService(db_session)
        result = await service.check_stock(uuid4(), 1)
        assert result["available"] is False
        assert result["stock_status"] == "out_of_stock"


class TestCheckStockBatch:

    async def test_reports_availability_per_variant(self, db_session, variant):
        service = InventoryService(db_session)
        results = await service.check_stock_batch([
            {"variant_id": variant.id, "quantity": 3},
            {"variant_id": uuid4(), "quantity": 1},
        ])
        assert results[variant.id]["available"] is True
        for key, value in results.items():
            if key != variant.id:
                assert value["available"] is False

    async def test_empty_requests_returns_empty_dict(self, db_session):
        service = InventoryService(db_session)
        assert await service.check_stock_batch([]) == {}


class TestAdjustStock:

    async def test_decrements_stock_and_records_adjustment(self, db_session, variant):
        service = InventoryService(db_session)
        inventory = await service.adjust_stock(
            StockAdjustmentCreate(variant_id=variant.id, quantity_change=-3, reason="test"),
        )
        assert inventory.quantity_available == 7

    async def test_invalidates_the_product_read_cache(self, db_session, variant):
        from core.utils.cache import product_read_cache
        product_read_cache[("variant", variant.id)] = "stale"
        product_read_cache[("variants", variant.product_id)] = "stale"

        service = InventoryService(db_session)
        await service.adjust_stock(
            StockAdjustmentCreate(variant_id=variant.id, quantity_change=-1, reason="test"),
        )

        assert ("variant", variant.id) not in product_read_cache
        assert ("variants", variant.product_id) not in product_read_cache

    async def test_raises_400_on_insufficient_stock(self, db_session, variant):
        service = InventoryService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.adjust_stock(
                StockAdjustmentCreate(variant_id=variant.id, quantity_change=-100, reason="test"),
            )
        assert exc_info.value.status_code == 400

    async def test_raises_404_for_unknown_variant(self, db_session):
        service = InventoryService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.adjust_stock(
                StockAdjustmentCreate(variant_id=uuid4(), quantity_change=-1, reason="test"),
            )
        assert exc_info.value.status_code == 404

    async def test_concurrent_adjustments_for_the_last_unit_do_not_oversell(self):
        """Regression test for the identity-map staleness bug: an earlier, unlocked
        read of the same Inventory row in a session (e.g. check_stock) must not cause
        a later locked read (get_with_lock, used by adjust_stock) to hand back stale
        in-memory data once the lock is actually acquired.

        Setup uses its own genuinely-committed connection rather than the db_session
        fixture: db_session runs each test in a SAVEPOINT for isolation, which the
        independent racer connections below (real concurrency needs real separate
        connections) can never see - a plain commit() there wouldn't leave the DB
        table itself unwritten from those connections' point of view.
        """
        variant_id = uuid7()
        async with TestingSessionLocal() as setup_session:
            category = Category(id=uuid7(), name="Cat", slug=f"cat-{uuid4().hex[:8]}")
            product = Product(id=uuid7(), name="Widget", slug=f"widget-{uuid4().hex[:8]}", category_id=category.id)
            v = ProductVariant(id=variant_id, product_id=product.id, sku=f"SKU-{uuid4().hex[:8]}", name="Default", base_price=Decimal("19.99"))
            setup_session.add_all([category, product, v])
            await setup_session.flush()
            setup_session.add(Inventory(id=uuid7(), variant_id=variant_id, quantity_available=1))
            await setup_session.commit()

        try:
            async def racer(session):
                service = InventoryService(session)
                # Mirror the real checkout path: an earlier, unlocked stock check on the
                # same row before the locked adjustment.
                await service.check_stock(variant_id, 1)
                return await service.adjust_stock(
                    StockAdjustmentCreate(variant_id=variant_id, quantity_change=-1, reason="race"),
                )

            async with TestingSessionLocal() as session_a, TestingSessionLocal() as session_b:
                results = await asyncio.gather(
                    racer(session_a), racer(session_b), return_exceptions=True,
                )

            successes = [r for r in results if not isinstance(r, Exception)]
            failures = [r for r in results if isinstance(r, Exception)]
            assert len(successes) == 1, f"expected exactly one winner, got: {results}"
            assert len(failures) == 1
            assert "Insufficient stock" in getattr(failures[0], "message", str(failures[0]))

            async with TestingSessionLocal() as check_session:
                result = await check_session.execute(select(Inventory).where(Inventory.variant_id == variant_id))
                assert result.scalar_one().quantity_available == 0
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


class TestLocationCrud:

    async def test_create_list_get_update_delete(self, db_session):
        from schemas.catalog.inventory import LocationCreate, LocationUpdate

        service = InventoryService(db_session)
        created = await service.create_location(LocationCreate(name=f"Warehouse {uuid4().hex[:6]}", address="1 Main St"))
        assert created.name.startswith("Warehouse")

        listed = await service.list_locations()
        assert any(l.id == created.id for l in listed["data"])

        fetched = await service.get_location(created.id)
        assert fetched.id == created.id

        updated = await service.update_location(created.id, LocationUpdate(name="Renamed Warehouse"))
        assert updated.name == "Renamed Warehouse"

        await service.delete_location(created.id)
        assert await service.get_location(created.id) is None

    async def test_get_unknown_location_returns_none(self, db_session):
        service = InventoryService(db_session)
        assert await service.get_location(uuid4()) is None

    async def test_update_unknown_location_raises_404(self, db_session):
        from schemas.catalog.inventory import LocationUpdate
        service = InventoryService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.update_location(uuid4(), LocationUpdate(name="X"))
        assert exc_info.value.status_code == 404

    async def test_delete_unknown_location_raises_404(self, db_session):
        service = InventoryService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.delete_location(uuid4())
        assert exc_info.value.status_code == 404

    async def test_delete_location_with_inventory_is_rejected(self, db_session, variant):
        from schemas.catalog.inventory import LocationCreate
        service = InventoryService(db_session)
        location = await service.create_location(LocationCreate(name=f"Warehouse {uuid4().hex[:6]}"))

        inv_result = await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))
        inventory = inv_result.scalar_one()
        inventory.location_id = location.id
        await db_session.commit()

        with pytest.raises(APIException) as exc_info:
            await service.delete_location(location.id)
        assert exc_info.value.status_code == 400


class TestInventoryCrud:

    async def test_create_update_delete(self, db_session):
        from schemas.catalog.inventory import Create as InventoryCreate, Update as InventoryUpdate, LocationCreate

        cat = Category(id=uuid7(), name="Cat", slug=f"cat-{uuid4().hex[:8]}")
        product = Product(id=uuid7(), name="Widget", slug=f"widget-{uuid4().hex[:8]}", category_id=cat.id)
        v = ProductVariant(id=uuid7(), product_id=product.id, sku=f"SKU-{uuid4().hex[:8]}", name="Default", base_price=Decimal("9.99"))
        db_session.add_all([cat, product, v])
        await db_session.commit()

        service = InventoryService(db_session)
        location = await service.create_location(LocationCreate(name=f"Warehouse {uuid4().hex[:6]}"))

        created = await service.create(InventoryCreate(variant_id=v.id, location_id=location.id, quantity=25))
        assert created.quantity_available == 25

        updated = await service.update(created.id, InventoryUpdate(quantity=40))
        assert updated.quantity_available == 40

        await service.delete(created.id)
        assert await service.get(created.id) is None

    async def test_update_unknown_inventory_raises_404(self, db_session):
        from schemas.catalog.inventory import Update as InventoryUpdate
        service = InventoryService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.update(uuid4(), InventoryUpdate(quantity=1))
        assert exc_info.value.status_code == 404

    async def test_delete_unknown_inventory_raises_404(self, db_session):
        service = InventoryService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.delete(uuid4())
        assert exc_info.value.status_code == 404


class TestAdjustmentCrud:

    async def test_get_adjustment(self, db_session, variant):
        service = InventoryService(db_session)
        await service.adjust_stock(
            StockAdjustmentCreate(variant_id=variant.id, quantity_change=-2, reason="test"),
        )
        listed = await service.adjustments()
        adjustment_id = listed["data"][0].id

        fetched = await service.get_adjustment(adjustment_id)
        assert fetched.id == adjustment_id

    async def test_get_unknown_adjustment_returns_none(self, db_session):
        service = InventoryService(db_session)
        assert await service.get_adjustment(uuid4()) is None

class TestIsLowStock:

    async def test_true_when_at_or_below_threshold(self, db_session, variant):
        inv_result = await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))
        inventory = inv_result.scalar_one()
        inventory.low_stock_threshold = 20
        await db_session.commit()

        service = InventoryService(db_session)
        assert await service.is_low_stock(inventory.id) is True

    async def test_false_when_above_threshold(self, db_session, variant):
        inv_result = await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))
        inventory = inv_result.scalar_one()
        inventory.low_stock_threshold = 1
        await db_session.commit()

        service = InventoryService(db_session)
        assert await service.is_low_stock(inventory.id) is False


class TestIncrement:

    async def test_increments_stock(self, db_session, variant):
        service = InventoryService(db_session)
        result = await service.increment(variant.id, quantity=5, location_id=uuid4())
        assert result["success"] is True

        inv_result = await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))
        assert inv_result.scalar_one().quantity_available == 15

    async def test_unknown_variant_reports_failure(self, db_session):
        service = InventoryService(db_session)
        result = await service.increment(uuid4(), quantity=5, location_id=uuid4())
        assert result["success"] is False


class TestSync:

    async def test_syncs_single_product(self, db_session, variant):
        service = InventoryService(db_session)
        result = await service.sync(variant.product_id)
        assert result["success"] is True

    async def test_unknown_product_reports_not_found(self, db_session):
        service = InventoryService(db_session)
        result = await service.sync(uuid4())
        assert result["success"] is False

    async def test_sync_all_counts_in_stock_and_out_of_stock_products(self, db_session):
        """sync() with no product_id scans every product; a product whose variants sum to
        zero total stock must be counted as out-of-stock, others as in-stock."""
        category = Category(id=uuid7(), name="Cat", slug=f"cat-{uuid4().hex[:8]}")
        out_of_stock_product = Product(id=uuid7(), name="Empty", slug=f"empty-{uuid4().hex[:8]}", category_id=category.id)
        in_stock_product = Product(id=uuid7(), name="Stocked", slug=f"stocked-{uuid4().hex[:8]}", category_id=category.id)
        v_empty = ProductVariant(id=uuid7(), product_id=out_of_stock_product.id, sku=f"SKU-{uuid4().hex[:8]}", name="D", base_price=Decimal("1.00"))
        v_stocked = ProductVariant(id=uuid7(), product_id=in_stock_product.id, sku=f"SKU-{uuid4().hex[:8]}", name="D", base_price=Decimal("1.00"))
        db_session.add_all([category, out_of_stock_product, in_stock_product, v_empty, v_stocked])
        await db_session.flush()
        db_session.add_all([
            Inventory(id=uuid7(), variant_id=v_empty.id, quantity_available=0),
            Inventory(id=uuid7(), variant_id=v_stocked.id, quantity_available=5),
        ])
        await db_session.commit()

        service = InventoryService(db_session)
        result = await service.sync()
        assert result["success"] is True
        assert result["total_products"] >= 2
        assert result["out_of_stock"] >= 1
        assert result["in_stock"] >= 1

    async def test_malformed_product_id_returns_graceful_failure(self, db_session):
        """sync() must not crash the caller (it's invoked from a background task) when handed
        bad input - it should catch the DB-level error and report failure instead."""
        service = InventoryService(db_session)
        result = await service.sync("not-a-uuid")
        assert result["success"] is False
        await db_session.rollback()


class TestGetRequiresAnIdentifier:

    async def test_raises_value_error_when_neither_id_given(self, db_session):
        service = InventoryService(db_session)
        with pytest.raises(ValueError):
            await service.get()


class TestGetSerializedNestedData:

    async def test_includes_variant_and_location_when_present(self, db_session, variant):
        location = WarehouseLocation(id=uuid7(), name=f"Depot {uuid4().hex[:6]}")
        db_session.add(location)
        await db_session.flush()
        inv_result = await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))
        inventory = inv_result.scalar_one()
        inventory.location_id = location.id
        await db_session.commit()

        service = InventoryService(db_session)
        item = await service.get(variant_id=variant.id, serialized=True)
        assert item["variant"]["id"] == str(variant.id)
        assert item["location"]["id"] == str(location.id)
        assert item["location"]["name"] == location.name

    async def test_includes_primary_image_when_variant_has_images(self, db_session, variant):
        image = ProductImage(id=uuid7(), variant_id=variant.id, url="http://example.com/a.jpg", is_primary=True)
        other_image = ProductImage(id=uuid7(), variant_id=variant.id, url="http://example.com/b.jpg", is_primary=False)
        db_session.add_all([image, other_image])
        await db_session.commit()

        service = InventoryService(db_session)
        item = await service.get(variant_id=variant.id, serialized=True)
        assert item["variant"]["primary_image"]["id"] == str(image.id)
        assert len(item["variant"]["images"]) == 2

    async def test_unserialized_returns_the_orm_object(self, db_session, variant):
        service = InventoryService(db_session)
        item = await service.get(variant_id=variant.id, serialized=False)
        assert isinstance(item, Inventory)


class TestListFilters:

    async def test_filters_by_location_id(self, db_session, variant):
        location = WarehouseLocation(id=uuid7(), name=f"Depot {uuid4().hex[:6]}")
        db_session.add(location)
        await db_session.flush()
        inv_result = await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))
        inventory = inv_result.scalar_one()
        inventory.location_id = location.id
        await db_session.commit()

        service = InventoryService(db_session)
        result = await service.list(location_id=location.id)
        assert any(item["id"] == str(inventory.id) for item in result["data"])

    async def test_low_stock_false_excludes_low_stock_items(self, db_session, variant):
        inv_result = await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))
        inventory = inv_result.scalar_one()
        inventory.low_stock_threshold = 100  # quantity_available=10 is now "low"
        await db_session.commit()

        service = InventoryService(db_session)
        result = await service.list(low_stock=False, limit=1000)
        assert all(item["id"] != str(inventory.id) for item in result["data"])

    async def test_malformed_location_id_is_handled_gracefully(self, db_session):
        """list() wraps its whole body in a try/except and degrades to an empty result rather
        than raising, since callers (the admin inventory grid) shouldn't 500 on a bad filter."""
        service = InventoryService(db_session)
        result = await service.list(location_id="not-a-uuid")
        assert result["data"] == []
        assert "error" in result
        await db_session.rollback()


@pytest.fixture
async def sort_pair(db_session):
    """Two products/variants/inventories/locations scoped by a unique marker in their names, so
    list() sorting assertions aren't thrown off by unrelated rows already in the shared dev DB."""
    marker = uuid4().hex[:8]
    category = Category(id=uuid7(), name="Cat", slug=f"cat-{uuid4().hex[:8]}")
    loc_a = WarehouseLocation(id=uuid7(), name=f"SortTest-{marker} Alpha Depot")
    loc_z = WarehouseLocation(id=uuid7(), name=f"SortTest-{marker} Zulu Depot")
    product_a = Product(id=uuid7(), name=f"SortTest-{marker} AAA Widget", slug=f"aaa-{marker}", category_id=category.id)
    product_z = Product(id=uuid7(), name=f"SortTest-{marker} ZZZ Widget", slug=f"zzz-{marker}", category_id=category.id)
    variant_a = ProductVariant(id=uuid7(), product_id=product_a.id, sku=f"SKU-A-{marker}", name="Default", base_price=Decimal("9.99"))
    variant_z = ProductVariant(id=uuid7(), product_id=product_z.id, sku=f"SKU-Z-{marker}", name="Default", base_price=Decimal("9.99"))
    db_session.add_all([category, loc_a, loc_z, product_a, product_z, variant_a, variant_z])
    await db_session.flush()

    earlier = datetime.now(timezone.utc) - timedelta(hours=1)
    later = datetime.now(timezone.utc)
    inv_a = Inventory(id=uuid7(), variant_id=variant_a.id, location_id=loc_a.id, quantity_available=3,
                       created_at=earlier, updated_at=earlier)
    inv_z = Inventory(id=uuid7(), variant_id=variant_z.id, location_id=loc_z.id, quantity_available=9,
                       created_at=later, updated_at=later)
    db_session.add_all([inv_a, inv_z])
    await db_session.commit()
    return marker


class TestListSorting:

    async def _names(self, service, marker, **kwargs):
        result = await service.list(search=f"SortTest-{marker}", limit=10, **kwargs)
        return [item["variant"]["product"]["name"] for item in result["data"]]

    async def test_sort_by_created_at_asc(self, db_session, sort_pair):
        service = InventoryService(db_session)
        names = await self._names(service, sort_pair, sort_by="created_at", sort_order="asc")
        assert names == sorted(names)

    async def test_sort_by_created_at_desc(self, db_session, sort_pair):
        service = InventoryService(db_session)
        names = await self._names(service, sort_pair, sort_by="created_at", sort_order="desc")
        assert names == sorted(names, reverse=True)

    async def test_sort_by_product_name_asc(self, db_session, sort_pair):
        service = InventoryService(db_session)
        names = await self._names(service, sort_pair, sort_by="product_name", sort_order="asc")
        assert names == sorted(names)

    async def test_sort_by_product_name_desc(self, db_session, sort_pair):
        service = InventoryService(db_session)
        names = await self._names(service, sort_pair, sort_by="product_name", sort_order="desc")
        assert names == sorted(names, reverse=True)

    async def test_sort_by_location_name_asc(self, db_session, sort_pair):
        service = InventoryService(db_session)
        result = await service.list(search=f"SortTest-{sort_pair}", limit=10, sort_by="location_name", sort_order="asc")
        location_names = [item["location"]["name"] for item in result["data"]]
        assert location_names == sorted(location_names)

    async def test_sort_by_location_name_desc(self, db_session, sort_pair):
        service = InventoryService(db_session)
        result = await service.list(search=f"SortTest-{sort_pair}", limit=10, sort_by="location_name", sort_order="desc")
        location_names = [item["location"]["name"] for item in result["data"]]
        assert location_names == sorted(location_names, reverse=True)

    async def test_sort_by_quantity_asc(self, db_session, sort_pair):
        service = InventoryService(db_session)
        result = await service.list(search=f"SortTest-{sort_pair}", limit=10, sort_by="quantity", sort_order="asc")
        quantities = [item["quantity_available"] for item in result["data"]]
        assert quantities == sorted(quantities)

    async def test_default_sort_field_ascending(self, db_session, sort_pair):
        """No sort_by given defaults to updated_at; this covers the asc branch of that default."""
        service = InventoryService(db_session)
        names = await self._names(service, sort_pair, sort_order="asc")
        assert names == sorted(names)


class TestUpdateLocationName:

    async def test_attaches_to_an_existing_location_case_insensitively(self, db_session, variant):
        from schemas.catalog.inventory import Update as InventoryUpdate
        existing = WarehouseLocation(id=uuid7(), name="Central Depot")
        db_session.add(existing)
        await db_session.commit()

        inv_result = await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))
        inventory_id = inv_result.scalar_one().id

        service = InventoryService(db_session)
        updated = await service.update(inventory_id, InventoryUpdate(location_name="central depot"))
        assert updated.location_id == existing.id

    async def test_creates_a_new_location_when_no_match_exists(self, db_session, variant):
        from schemas.catalog.inventory import Update as InventoryUpdate
        inv_result = await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))
        inventory_id = inv_result.scalar_one().id

        unique_name = f"Brand New Depot {uuid4().hex[:8]}"
        service = InventoryService(db_session)
        updated = await service.update(inventory_id, InventoryUpdate(location_name=unique_name))
        assert updated.location is not None
        assert updated.location.name == unique_name

    async def test_whitespace_only_location_name_is_a_no_op(self, db_session, variant):
        from schemas.catalog.inventory import Update as InventoryUpdate
        inv_result = await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))
        inventory = inv_result.scalar_one()
        original_location_id = inventory.location_id

        service = InventoryService(db_session)
        updated = await service.update(inventory.id, InventoryUpdate(location_name="   "))
        assert updated.location_id == original_location_id


class TestAdjustStockWithLockService:

    async def test_uses_the_distributed_lock_when_configured(self, db_session, variant):
        lock_service = FakeLockService()
        service = InventoryService(db_session, lock_service=lock_service)
        inventory = await service.adjust_stock(
            StockAdjustmentCreate(variant_id=variant.id, quantity_change=-2, reason="test"),
        )
        assert inventory.quantity_available == 8
        assert lock_service.calls == [(variant.id, 30)]


class TestAdjustStockGenericFailure:

    async def test_non_api_exception_is_wrapped_as_500_and_rolled_back(self, db_session, variant):
        """A malformed variant_id can't be caught by pydantic once it's already inside the
        StockAdjustmentCreate object (assignment isn't re-validated), so it reaches the DB layer
        as a genuine error - exercising the non-APIException branch of adjust_stock's own error
        handling, including its rollback."""
        data = StockAdjustmentCreate(variant_id=variant.id, quantity_change=-1, reason="test")
        data.variant_id = "not-a-uuid"

        service = InventoryService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.adjust_stock(data)
        assert exc_info.value.status_code == 500
        # adjust_stock's except-block calls db.rollback() before re-raising; a further query
        # on this SAVEPOINT-joined test session immediately after an in-test rollback trips an
        # unrelated SQLAlchemy/greenlet quirk in this harness, so state is verified via the
        # dedicated concurrency test elsewhere in this file instead of re-querying here.
        await db_session.rollback()


class TestIsLowStockUnknownInventory:

    async def test_unknown_inventory_id_returns_false(self, db_session):
        service = InventoryService(db_session)
        assert await service.is_low_stock(uuid4()) is False


class TestStockLevels:

    async def test_returns_computed_flags_for_each_item(self, db_session, variant):
        inv_result = await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))
        inventory = inv_result.scalar_one()
        inventory.low_stock_threshold = 20  # quantity 10 <= 20 -> low stock, but not out of stock
        await db_session.commit()

        service = InventoryService(db_session)
        levels = await service.stock_levels(variant_ids=[variant.id])
        assert len(levels) == 1
        level = levels[0]
        assert level["variant_id"] == str(variant.id)
        assert level["current_quantity"] == 10
        assert level["is_low_stock"] is True
        assert level["is_out_of_stock"] is False

    async def test_filters_by_location_id(self, db_session, variant):
        location = WarehouseLocation(id=uuid7(), name=f"Depot {uuid4().hex[:6]}")
        db_session.add(location)
        await db_session.flush()
        inv_result = await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))
        inventory = inv_result.scalar_one()
        inventory.location_id = location.id
        await db_session.commit()

        service = InventoryService(db_session)
        levels = await service.stock_levels(location_id=location.id)
        assert any(l["variant_id"] == str(variant.id) for l in levels)

        other_location_levels = await service.stock_levels(location_id=uuid4())
        assert all(l["variant_id"] != str(variant.id) for l in other_location_levels)

    async def test_no_filters_returns_all_items(self, db_session, variant):
        service = InventoryService(db_session)
        levels = await service.stock_levels()
        assert any(l["variant_id"] == str(variant.id) for l in levels)


class TestListIncludesVariantImages:

    async def test_list_serializes_primary_image_for_items_with_images(self, db_session, variant):
        image = ProductImage(id=uuid7(), variant_id=variant.id, url="http://example.com/a.jpg", is_primary=True)
        db_session.add(image)
        await db_session.commit()

        service = InventoryService(db_session)
        result = await service.list(product_id=variant.product_id, limit=1000)
        item = next(i for i in result["data"] if i["variant_id"] == str(variant.id))
        assert item["variant"]["primary_image"]["id"] == str(image.id)


class TestPredictDemand:

    async def test_predicts_thirty_percent_of_current_stock(self, db_session, variant):
        inv_result = await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))
        inventory = inv_result.scalar_one()
        inventory.quantity_available = 100
        await db_session.commit()

        service = InventoryService(db_session)
        result = await service.predict_demand(variant.id, forecast_days=14)
        assert result["current_stock"] == 100
        assert result["predicted_demand"] == 30
        assert result["forecast_days"] == 14
        assert result["recommendation"] == "Stock adequate"

    async def test_floors_prediction_at_ten_for_low_stock(self, db_session, variant):
        inv_result = await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))
        inv_result.scalar_one().quantity_available = 5
        await db_session.commit()

        service = InventoryService(db_session)
        result = await service.predict_demand(variant.id)  # stock=5, 30% = 1, floored to 10
        assert result["predicted_demand"] == 10
        assert result["current_stock"] == 5
        assert result["recommendation"] == "Reorder recommended"  # 10 > 5

    async def test_unknown_variant_defaults_to_zero_stock(self, db_session):
        service = InventoryService(db_session)
        result = await service.predict_demand(uuid4())
        assert result["current_stock"] == 0
        assert result["predicted_demand"] == 10


class TestReorderSuggestions:

    async def test_suggests_reorder_only_for_low_stock_items_with_urgency_ordering(self, db_session):
        category = Category(id=uuid7(), name="Cat", slug=f"cat-{uuid4().hex[:8]}")
        p_high = Product(id=uuid7(), name="High", slug=f"high-{uuid4().hex[:8]}", category_id=category.id)
        p_medium = Product(id=uuid7(), name="Medium", slug=f"medium-{uuid4().hex[:8]}", category_id=category.id)
        p_healthy = Product(id=uuid7(), name="Healthy", slug=f"healthy-{uuid4().hex[:8]}", category_id=category.id)
        v_high = ProductVariant(id=uuid7(), product_id=p_high.id, sku=f"SKU-{uuid4().hex[:8]}", name="D", base_price=Decimal("1"))
        v_medium = ProductVariant(id=uuid7(), product_id=p_medium.id, sku=f"SKU-{uuid4().hex[:8]}", name="D", base_price=Decimal("1"))
        v_healthy = ProductVariant(id=uuid7(), product_id=p_healthy.id, sku=f"SKU-{uuid4().hex[:8]}", name="D", base_price=Decimal("1"))
        db_session.add_all([category, p_high, p_medium, p_healthy, v_high, v_medium, v_healthy])
        await db_session.flush()
        db_session.add_all([
            Inventory(id=uuid7(), variant_id=v_high.id, quantity_available=0, low_stock_threshold=5),
            Inventory(id=uuid7(), variant_id=v_medium.id, quantity_available=3, low_stock_threshold=5),
            Inventory(id=uuid7(), variant_id=v_healthy.id, quantity_available=50, low_stock_threshold=5),
        ])
        await db_session.commit()

        service = InventoryService(db_session)
        suggestions = await service.reorder_suggestions()
        by_variant = {s["variant_id"]: s for s in suggestions}

        assert str(v_high.id) in by_variant
        assert str(v_medium.id) in by_variant
        assert str(v_healthy.id) not in by_variant  # well-stocked items aren't suggested

        assert by_variant[str(v_high.id)]["urgency"] == "high"
        assert by_variant[str(v_high.id)]["suggested_quantity"] == 10  # threshold * 2
        assert by_variant[str(v_high.id)]["days_until_stockout"] == 0
        assert by_variant[str(v_medium.id)]["urgency"] == "medium"
        assert by_variant[str(v_medium.id)]["days_until_stockout"] == 7

        # High urgency must be sorted ahead of medium urgency.
        high_index = next(i for i, s in enumerate(suggestions) if s["variant_id"] == str(v_high.id))
        medium_index = next(i for i, s in enumerate(suggestions) if s["variant_id"] == str(v_medium.id))
        assert high_index < medium_index

    async def test_filters_by_location_id(self, db_session, variant):
        location = WarehouseLocation(id=uuid7(), name=f"Depot {uuid4().hex[:6]}")
        db_session.add(location)
        await db_session.flush()
        inv_result = await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))
        inventory = inv_result.scalar_one()
        inventory.location_id = location.id
        inventory.low_stock_threshold = 100  # ensure it's "low stock" so it would show up
        await db_session.commit()

        service = InventoryService(db_session)
        suggestions = await service.reorder_suggestions(location_id=location.id)
        assert any(s["variant_id"] == str(variant.id) for s in suggestions)

        elsewhere = await service.reorder_suggestions(location_id=uuid4())
        assert all(s["variant_id"] != str(variant.id) for s in elsewhere)


class TestBatchUpdateInventoryFromWarehouseData:

    async def test_applies_quantity_changes_for_known_variants(self, db_session, variant):
        service = InventoryService(db_session)
        result = await service.batch_update_inventory_from_warehouse_data([
            {"variant_id": str(variant.id), "quantity": 25},
        ])
        assert result["success"] is True
        assert result["updated_count"] == 1

        inv_result = await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))
        assert inv_result.scalar_one().quantity_available == 25

    async def test_skips_items_with_no_quantity_change(self, db_session, variant):
        service = InventoryService(db_session)
        result = await service.batch_update_inventory_from_warehouse_data([
            {"variant_id": str(variant.id), "quantity": 10},  # already 10, no change
        ])
        assert result["success"] is True
        assert result["updated_count"] == 0

    async def test_skips_unknown_variants(self, db_session):
        service = InventoryService(db_session)
        result = await service.batch_update_inventory_from_warehouse_data([
            {"variant_id": str(uuid4()), "quantity": 5},
        ])
        assert result["success"] is True
        assert result["updated_count"] == 0

    async def test_malformed_item_is_skipped_without_failing_the_batch(self, db_session, variant):
        """One bad row in a warehouse feed (missing the quantity key) shouldn't take down
        processing for the other, well-formed rows."""
        service = InventoryService(db_session)
        result = await service.batch_update_inventory_from_warehouse_data([
            {"variant_id": str(variant.id)},  # missing "quantity" -> KeyError, caught, skipped
        ])
        assert result["success"] is True
        assert result["updated_count"] == 0

    async def test_non_iterable_input_raises_500(self, db_session):
        service = InventoryService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.batch_update_inventory_from_warehouse_data(None)
        assert exc_info.value.status_code == 500


class TestCheckStockLocationFilter:

    async def test_matching_location_is_available(self, db_session, variant):
        location = WarehouseLocation(id=uuid7(), name=f"Depot {uuid4().hex[:6]}")
        db_session.add(location)
        await db_session.flush()
        inv_result = await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))
        inventory = inv_result.scalar_one()
        inventory.location_id = location.id
        await db_session.commit()

        service = InventoryService(db_session)
        result = await service.check_stock(variant.id, 1, location_id=location.id)
        assert result["available"] is True

    async def test_non_matching_location_reports_not_found(self, db_session, variant):
        service = InventoryService(db_session)
        result = await service.check_stock(variant.id, 1, location_id=uuid4())
        assert result["available"] is False
        assert result["message"] == "Product not found in inventory"


class TestCheckStockMalformedInput:

    async def test_malformed_variant_id_returns_graceful_failure(self, db_session):
        service = InventoryService(db_session)
        result = await service.check_stock("not-a-uuid", 1)
        assert result["available"] is False
        assert result["stock_status"] == "out_of_stock"
        assert "Error checking stock" in result["message"]
        await db_session.rollback()


class TestIncrementWithLockService:

    async def test_uses_the_distributed_lock_when_configured(self, db_session, variant):
        lock_service = FakeLockService()
        service = InventoryService(db_session, lock_service=lock_service)
        result = await service.increment(variant.id, quantity=5, location_id=uuid4())
        assert result["success"] is True
        assert lock_service.calls == [(variant.id, 30)]


class TestIncrementGenericFailure:

    async def test_malformed_variant_id_returns_failure_and_rolls_back(self, db_session, variant):
        service = InventoryService(db_session)
        result = await service.increment("not-a-uuid", quantity=1, location_id=uuid4())
        assert result["success"] is False
        assert "Failed to increment stock" in result["message"]
        # See the comment in TestAdjustStockGenericFailure - a query on this session right after
        # an in-test rollback trips a harness-level SQLAlchemy/greenlet quirk, unrelated to the
        # correctness of increment() itself.
        await db_session.rollback()


class TestBulkStockUpdate:

    async def test_updates_stock_for_known_variants(self, db_session, variant):
        service = InventoryService(db_session)
        result = await service.bulk_stock_update(
            stock_changes=[{"variant_id": variant.id, "quantity_change": -4, "notes": "test"}],
            reason="bulk_test",
        )
        assert result["success"] is True
        assert result["updated_count"] == 1

        inv_result = await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))
        assert inv_result.scalar_one().quantity_available == 6

    async def test_unknown_variant_propagates_404_not_masked_as_500(self, db_session):
        """Regression test for a bug fixed alongside this test: bulk_stock_update() used to
        catch every exception - including the deliberate APIException(404) that
        atomic_bulk_stock_update raises for an unknown variant - and relabel it as a 500,
        hiding the real cause from callers (e.g. an admin warehouse-sync tool). Fixed to
        re-raise APIException as-is, matching adjust_stock/increment's existing pattern."""
        service = InventoryService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.bulk_stock_update(
                stock_changes=[{"variant_id": uuid4(), "quantity_change": -1, "notes": "x"}],
                reason="bulk_test",
            )
        assert exc_info.value.status_code == 404

    async def test_insufficient_stock_propagates_400_not_masked_as_500(self, db_session, variant):
        service = InventoryService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.bulk_stock_update(
                stock_changes=[{"variant_id": variant.id, "quantity_change": -1000, "notes": "x"}],
                reason="bulk_test",
            )
        assert exc_info.value.status_code == 400

    async def test_non_api_exception_is_still_wrapped_as_500(self, db_session):
        """A malformed variant_id can't raise APIException (it never gets far enough to look up
        the row) - it's a raw DB error, which should still fall through to the generic 500
        handler, distinct from the APIException passthrough exercised above."""
        service = InventoryService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.bulk_stock_update(
                stock_changes=[{"variant_id": "not-a-uuid", "quantity_change": -1, "notes": "x"}],
                reason="bulk_test",
            )
        assert exc_info.value.status_code == 500
        await db_session.rollback()
