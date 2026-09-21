"""Tests for services/catalog/inventory.py - InventoryService.

Focused on check_stock, adjust_stock, and the row-locking behavior that
checkout relies on to avoid overselling under concurrent requests.
"""

import asyncio
import pytest
from uuid import uuid4
from decimal import Decimal
from sqlalchemy import select

from core.exceptions import APIException
from core.utils.uuid_utils import uuid7
from services.catalog.inventory import InventoryService
from schemas.catalog.inventory import AdjustmentCreate as StockAdjustmentCreate
from models.catalog.category import Category
from models.catalog.product import Product, ProductVariant
from models.catalog.inventories import Inventory, StockAdjustment
from tests.conftest import TestingSessionLocal


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
