"""Tests for services/commerce/shipping.py - ShippingService.

calc_cost() is the highest-value target: it's what OrderService relies on to
price shipping at checkout, with a "cheapest available method" fallback when
no method_id (or an inactive one) is given.
"""

import pytest
from uuid import uuid4
from sqlalchemy import delete, update

from core.exceptions import APIException
from services.commerce.shipping import ShippingService
from models.commerce.shipping import ShippingMethod
from models.commerce.subscriptions import Subscription
from schemas.commerce.shipping import MethodCreate as ShippingMethodCreate, MethodUpdate as ShippingMethodUpdate


@pytest.fixture(autouse=True)
async def _clean_shipping_methods(db_session):
    """calc_cost()'s cheapest-method fallback queries every active
    ShippingMethod - rows created by earlier tests (real commits, not rolled
    back) would otherwise leak into later "cheapest"/"none exist" assertions.
    No other test file uses ShippingMethod and no migration seeds it."""
    # Subscriptions point at methods; detach them first (all of this rolls back after the test).
    await db_session.execute(update(Subscription).values(shipping_method_id=None))
    await db_session.execute(delete(ShippingMethod))
    await db_session.commit()
    yield


def make_create(name=None, price=10.0, estimated_days=3, is_active=True) -> ShippingMethodCreate:
    return ShippingMethodCreate(
        name=name or f"Method {uuid4().hex[:8]}", price=price,
        estimated_days=estimated_days, is_active=is_active,
    )


class TestCreate:

    async def test_creates_a_shipping_method(self, db_session):
        service = ShippingService(db_session)
        method = await service.create(make_create(name="Standard", price=5.99))
        assert method.name == "Standard"
        assert float(method.price) == pytest.approx(5.99)


class TestGetAndList:

    async def test_gets_by_id(self, db_session):
        service = ShippingService(db_session)
        created = await service.create(make_create())
        found = await service.get(created.id)
        assert found.id == created.id

    async def test_unknown_id_returns_none(self, db_session):
        service = ShippingService(db_session)
        assert await service.get(uuid4()) is None

    async def test_list_active_only_excludes_inactive(self, db_session):
        service = ShippingService(db_session)
        active = await service.create(make_create(is_active=True))
        inactive = await service.create(make_create(is_active=False))

        results = await service.list(active_only=True)
        ids = [m.id for m in results]
        assert active.id in ids
        assert inactive.id not in ids


class TestGetAllMethods:

    async def test_paginates_and_reports_total(self, db_session):
        service = ShippingService(db_session)
        for _ in range(3):
            await service.create(make_create())

        result = await service.get_all_methods(page=1, limit=2)
        assert len(result["items"]) <= 2
        assert result["total"] >= 3
        assert result["page"] == 1

    async def test_filters_by_is_active(self, db_session):
        service = ShippingService(db_session)
        created = await service.create(make_create(is_active=False))

        result = await service.get_all_methods(is_active=False, limit=100)
        ids = [m.id for m in result["items"]]
        assert created.id in ids


class TestCalcCost:

    async def test_uses_the_specified_active_method(self, db_session):
        service = ShippingService(db_session)
        method = await service.create(make_create(price=15.0))
        cost = await service.calc_cost(shipping_method_id=method.id)
        assert float(cost) == pytest.approx(15.0)

    async def test_falls_back_to_cheapest_when_no_method_specified(self, db_session):
        service = ShippingService(db_session)
        await service.create(make_create(price=20.0))
        cheap = await service.create(make_create(price=3.0))

        cost = await service.calc_cost()
        assert float(cost) == pytest.approx(3.0)

    async def test_falls_back_to_cheapest_when_specified_method_is_inactive(self, db_session):
        service = ShippingService(db_session)
        inactive = await service.create(make_create(price=1.0, is_active=False))
        cheapest_active = await service.create(make_create(price=8.0))

        cost = await service.calc_cost(shipping_method_id=inactive.id)
        assert float(cost) == pytest.approx(8.0)

    async def test_returns_zero_when_no_methods_exist(self, db_session):
        service = ShippingService(db_session)
        cost = await service.calc_cost(shipping_method_id=uuid4())
        assert cost == 0.0


class TestUpdate:

    async def test_updates_fields(self, db_session):
        service = ShippingService(db_session)
        created = await service.create(make_create())
        updated = await service.update(created.id, ShippingMethodUpdate(name="Renamed"))
        assert updated.name == "Renamed"

    async def test_unknown_id_raises_404(self, db_session):
        service = ShippingService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.update(uuid4(), ShippingMethodUpdate(name="Nope"))
        assert exc_info.value.status_code == 404


class TestDelete:

    async def test_deletes_a_method(self, db_session):
        service = ShippingService(db_session)
        created = await service.create(make_create())
        assert await service.delete(created.id) is True
        assert await service.get(created.id) is None

    async def test_unknown_id_returns_false(self, db_session):
        service = ShippingService(db_session)
        assert await service.delete(uuid4()) is False
