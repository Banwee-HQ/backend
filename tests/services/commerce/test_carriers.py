"""Tests for services/commerce/carriers.py - CarrierService.

The carriers table ships pre-seeded with real carriers (ups, fedex, dhl,
etc. - see the 2026_04_22_add_carriers_table migration), so every test
here uses a unique code to avoid colliding with that seed data or with
carriers created by other tests in the same run.
"""

import pytest
from uuid import uuid4

from core.exceptions import APIException
from services.commerce.carriers import CarrierService
from schemas.commerce.carrier import Create as CarrierCreate, Update as CarrierUpdate
from models.commerce.shipping_tracking import ShippingProvider


def make_create(code=None, name="Test Carrier") -> CarrierCreate:
    return CarrierCreate(code=code or f"test-{uuid4().hex[:8]}", name=name)


class TestCreate:

    async def test_creates_a_carrier(self, db_session):
        service = CarrierService(db_session)
        carrier = await service.create(make_create())
        assert carrier.id is not None
        assert carrier.is_active is True

    async def test_duplicate_code_is_rejected(self, db_session):
        service = CarrierService(db_session)
        code = f"dup-{uuid4().hex[:8]}"
        await service.create(make_create(code=code))
        with pytest.raises(APIException) as exc_info:
            await service.create(make_create(code=code))
        assert exc_info.value.status_code == 400


class TestUpdate:

    async def test_updates_fields(self, db_session):
        service = CarrierService(db_session)
        carrier = await service.create(make_create())
        updated = await service.update(carrier.id, CarrierUpdate(name="Renamed Carrier"))
        assert updated.name == "Renamed Carrier"

    async def test_unknown_id_returns_none(self, db_session):
        service = CarrierService(db_session)
        result = await service.update(uuid4(), CarrierUpdate(name="Nope"))
        assert result is None


class TestDelete:

    async def test_deletes_an_unreferenced_carrier(self, db_session):
        service = CarrierService(db_session)
        carrier = await service.create(make_create())
        assert await service.delete(carrier.id) is True
        assert await service.get(carrier.id) is None

    async def test_unknown_id_returns_false(self, db_session):
        service = CarrierService(db_session)
        assert await service.delete(uuid4()) is False

    async def test_cannot_delete_a_carrier_referenced_by_a_provider(self, db_session):
        service = CarrierService(db_session)
        carrier = await service.create(make_create())
        provider = ShippingProvider(
            id=uuid4(), carrier_id=carrier.id, name="Test Provider", is_active=True,
            api_url="https://example.com/api", tracking_url_template="https://example.com/track/{tracking_number}",
        )
        db_session.add(provider)
        await db_session.commit()

        with pytest.raises(APIException) as exc_info:
            await service.delete(carrier.id)
        assert exc_info.value.status_code == 400


class TestGetByCode:

    async def test_finds_by_code(self, db_session):
        service = CarrierService(db_session)
        code = f"find-{uuid4().hex[:8]}"
        carrier = await service.create(make_create(code=code))
        found = await service.get_by_code(code)
        assert found.id == carrier.id

    async def test_active_only_excludes_inactive_carrier(self, db_session):
        service = CarrierService(db_session)
        code = f"inactive-{uuid4().hex[:8]}"
        carrier = await service.create(make_create(code=code))
        await service.update(carrier.id, CarrierUpdate(is_active=False))

        found = await service.get_by_code(code, active_only=True)
        assert found is None
