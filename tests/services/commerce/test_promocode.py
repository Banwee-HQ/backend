"""Tests for services/commerce/promocode.py - PromocodeService.

validate() is the highest-value target: it's the gate cart.py's apply_promo
relies on, and covers date-window, usage-limit, and active-flag checks that
aren't exercised by simple CRUD tests. inc_usage() is tested for the
auto-deactivate-on-limit-reached behavior, which is easy to get off-by-one.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timedelta, timezone

from core.exceptions import APIException
from services.commerce.promocode import PromocodeService
from schemas.commerce.promos import Create as PromocodeCreate, Update as PromocodeUpdate


def make_create(code=None, value=10.0, usage_limit=None, valid_from=None, valid_until=None) -> PromocodeCreate:
    return PromocodeCreate(
        code=code or f"PROMO{uuid4().hex[:8].upper()}",
        discount_type="percentage",
        value=value,
        usage_limit=usage_limit,
        valid_from=valid_from,
        valid_until=valid_until,
    )


class TestValidate:

    async def test_valid_active_promocode(self, db_session):
        service = PromocodeService(db_session)
        created = await service.create(make_create())
        is_valid, error, promo = await service.validate(created.code)
        assert is_valid is True
        assert error is None
        assert promo.id == created.id

    async def test_unknown_code_is_invalid(self, db_session):
        service = PromocodeService(db_session)
        is_valid, error, promo = await service.validate("NOSUCHCODE")
        assert is_valid is False
        assert promo is None

    async def test_not_yet_valid_is_rejected(self, db_session):
        service = PromocodeService(db_session)
        created = await service.create(make_create(valid_from=datetime.now(timezone.utc) + timedelta(days=1)))
        is_valid, error, promo = await service.validate(created.code)
        assert is_valid is False
        assert "not yet valid" in error

    async def test_expired_is_rejected(self, db_session):
        service = PromocodeService(db_session)
        created = await service.create(make_create(valid_until=datetime.now(timezone.utc) - timedelta(days=1)))
        is_valid, error, promo = await service.validate(created.code)
        assert is_valid is False
        assert "expired" in error

    async def test_usage_limit_reached_is_rejected(self, db_session):
        """inc_usage() auto-deactivates on limit reached, so the active_only lookup in
        validate() excludes it before ever reaching its own usage_limit check - the
        promocode is still correctly rejected, just via the not-found path."""
        service = PromocodeService(db_session)
        created = await service.create(make_create(usage_limit=1))
        await service.inc_usage(created.id)
        is_valid, error, promo = await service.validate(created.code)
        assert is_valid is False
        assert promo is None


    async def test_usage_limit_check_inside_validate_when_still_flagged_active(self, db_session):
        """Exercises validate()'s own usage_limit branch directly (used_count at the
        limit but is_active untouched) - the case inc_usage's auto-deactivate normally
        preempts."""
        service = PromocodeService(db_session)
        created = await service.create(make_create(usage_limit=1))
        created.used_count = 1
        await db_session.commit()

        is_valid, error, promo = await service.validate(created.code)
        assert is_valid is False
        assert "usage limit" in error


class TestIncUsage:

    async def test_increments_used_count(self, db_session):
        service = PromocodeService(db_session)
        created = await service.create(make_create())
        updated = await service.inc_usage(created.id)
        assert updated.used_count == 1

    async def test_deactivates_when_usage_limit_reached(self, db_session):
        service = PromocodeService(db_session)
        created = await service.create(make_create(usage_limit=2))
        await service.inc_usage(created.id)
        second = await service.inc_usage(created.id)
        assert second.used_count == 2
        assert second.is_active is False

    async def test_stays_active_below_usage_limit(self, db_session):
        service = PromocodeService(db_session)
        created = await service.create(make_create(usage_limit=5))
        updated = await service.inc_usage(created.id)
        assert updated.is_active is True

    async def test_unknown_id_raises_404(self, db_session):
        service = PromocodeService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.inc_usage(uuid4())
        assert exc_info.value.status_code == 404


class TestGet:

    async def test_requires_id_or_code(self, db_session):
        """get() with neither promocode_id nor code raises rather than silently
        returning None - callers rely on the ValueError, not a None/empty result."""
        service = PromocodeService(db_session)
        with pytest.raises(ValueError):
            await service.get()


class TestUpdate:

    async def test_updates_fields(self, db_session):
        service = PromocodeService(db_session)
        created = await service.create(make_create())
        updated = await service.update(created.id, PromocodeUpdate(value=99))
        assert updated.value == 99

    async def test_unknown_id_raises_404(self, db_session):
        service = PromocodeService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.update(uuid4(), PromocodeUpdate(value=1))
        assert exc_info.value.status_code == 404


class TestDelete:

    async def test_deletes_existing_promocode(self, db_session):
        service = PromocodeService(db_session)
        created = await service.create(make_create())
        assert await service.delete(created.id) is True
        assert await service.get(created.id) is None

    async def test_unknown_id_returns_false(self, db_session):
        service = PromocodeService(db_session)
        assert await service.delete(uuid4()) is False
