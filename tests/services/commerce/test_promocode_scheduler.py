"""Tests for services/commerce/promocode_scheduler.py - PromoCodeScheduler.

update_promocode_statuses()/list() scan the whole promocodes table with no
per-test scoping, and Promocode rows commit for real (persisting across the
whole test run) - so assertions here check the specific test-created code's
state and presence/absence in the results list, not exact activated/
deactivated counts (which would include whatever stray rows other tests in
this run happen to have left behind).
"""

import pytest
from uuid import uuid4
from datetime import datetime, timedelta, timezone

from services.commerce.promocode_scheduler import PromoCodeScheduler
from models.commerce.promocode import Promocode


async def make_promocode(db_session, is_active=True, **overrides) -> Promocode:
    fields = {
        "id": uuid4(),
        "code": f"SCHED{uuid4().hex[:8].upper()}",
        "discount_type": "percentage",
        "value": 10,
        "is_active": is_active,
    }
    fields.update(overrides)
    promo = Promocode(**fields)
    db_session.add(promo)
    await db_session.commit()
    await db_session.refresh(promo)
    return promo


class TestUpdatePromocodeStatuses:

    async def test_activates_promocode_whose_valid_from_has_arrived(self, db_session):
        now = datetime.now(timezone.utc)
        promo = await make_promocode(db_session, is_active=False, valid_from=now - timedelta(days=1),
                                      valid_until=now + timedelta(days=30))
        scheduler = PromoCodeScheduler(db_session)

        result = await scheduler.update_promocode_statuses()

        assert result["success"] is True
        await db_session.refresh(promo)
        assert promo.is_active is True
        assert any(r["code"] == promo.code and r["action"] == "activated" for r in result["results"])

    async def test_deactivates_expired_promocode(self, db_session):
        now = datetime.now(timezone.utc)
        promo = await make_promocode(db_session, is_active=True, valid_until=now - timedelta(days=1))
        scheduler = PromoCodeScheduler(db_session)

        result = await scheduler.update_promocode_statuses()

        await db_session.refresh(promo)
        assert promo.is_active is False
        assert any(r["code"] == promo.code and r["reason"] == "expired" for r in result["results"])

    async def test_deactivates_promocode_that_reached_usage_limit(self, db_session):
        promo = await make_promocode(db_session, is_active=True, usage_limit=5, used_count=5)
        scheduler = PromoCodeScheduler(db_session)

        result = await scheduler.update_promocode_statuses()

        await db_session.refresh(promo)
        assert promo.is_active is False
        assert any(r["code"] == promo.code and r["reason"] == "usage_limit_reached" for r in result["results"])

    async def test_deactivates_promocode_not_yet_valid(self, db_session):
        now = datetime.now(timezone.utc)
        promo = await make_promocode(db_session, is_active=True, valid_from=now + timedelta(days=1))
        scheduler = PromoCodeScheduler(db_session)

        result = await scheduler.update_promocode_statuses()

        await db_session.refresh(promo)
        assert promo.is_active is False
        assert any(r["code"] == promo.code and r["reason"] == "not_yet_valid" for r in result["results"])

    async def test_leaves_currently_valid_active_promocode_untouched(self, db_session):
        now = datetime.now(timezone.utc)
        promo = await make_promocode(db_session, is_active=True, valid_from=now - timedelta(days=1),
                                      valid_until=now + timedelta(days=30))
        scheduler = PromoCodeScheduler(db_session)

        result = await scheduler.update_promocode_statuses()

        await db_session.refresh(promo)
        assert promo.is_active is True
        assert not any(r["code"] == promo.code for r in result["results"])

    async def test_no_dates_or_limits_stays_active_and_untouched(self, db_session):
        promo = await make_promocode(db_session, is_active=True)
        scheduler = PromoCodeScheduler(db_session)

        result = await scheduler.update_promocode_statuses()

        await db_session.refresh(promo)
        assert promo.is_active is True
        assert not any(r["code"] == promo.code for r in result["results"])


class TestList:

    async def test_active_status_includes_currently_valid_promocode(self, db_session):
        promo = await make_promocode(db_session, is_active=True)
        scheduler = PromoCodeScheduler(db_session)

        results = await scheduler.list(status="active")
        assert any(p.code == promo.code for p in results)

    async def test_active_status_excludes_inactive_promocode(self, db_session):
        promo = await make_promocode(db_session, is_active=False)
        scheduler = PromoCodeScheduler(db_session)

        results = await scheduler.list(status="active")
        assert not any(p.code == promo.code for p in results)

    async def test_expired_status_includes_only_expired_promocodes(self, db_session):
        now = datetime.now(timezone.utc)
        expired = await make_promocode(db_session, is_active=True, valid_until=now - timedelta(days=1))
        active = await make_promocode(db_session, is_active=True, valid_until=now + timedelta(days=30))
        scheduler = PromoCodeScheduler(db_session)

        results = await scheduler.list(status="expired")
        codes = [p.code for p in results]
        assert expired.code in codes
        assert active.code not in codes

    async def test_all_status_includes_active_and_inactive(self, db_session):
        active = await make_promocode(db_session, is_active=True)
        inactive = await make_promocode(db_session, is_active=False)
        scheduler = PromoCodeScheduler(db_session)

        results = await scheduler.list(status="all")
        codes = [p.code for p in results]
        assert active.code in codes
        assert inactive.code in codes
