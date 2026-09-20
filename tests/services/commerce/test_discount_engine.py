"""Tests for the DB-backed parts of services/commerce/discounts.py - DiscountEngine.

test_discounts.py already covers calculate_discount_amount's pure math against
fake objects; this file covers validate_discount_code (regression coverage for
the bug where it was defined as get_discount but called as
validate_discount_code from services/commerce/orders.py - an AttributeError
that silently killed every subscription-discount checkout attempt),
select_optimal_discount, remove_expired_discounts (regression coverage for
its select(...).delete() misuse, which isn't valid SQLAlchemy and made the
method always fail whenever there was an actual expired discount to remove),
get_applicable_discounts, list, and create.
"""

import pytest
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timedelta, timezone

from services.commerce.discounts import DiscountEngine
from models.commerce.discounts import DiscountType


def date_range(days_valid=30):
    now = datetime.now(timezone.utc)
    return now - timedelta(days=1), now + timedelta(days=days_valid)


class TestCreate:

    async def test_creates_and_uppercases_code(self, db_session):
        engine = DiscountEngine(db_session)
        valid_from, valid_until = date_range()
        discount = await engine.create(
            code=f"save{uuid4().hex[:8]}", discount_type=DiscountType.PERCENTAGE.value,
            value=10, valid_from=valid_from, valid_until=valid_until,
        )
        assert discount.code == discount.code.upper()
        assert discount.is_active is True
        assert discount.used_count == 0


class TestValidateDiscountCode:

    async def test_valid_code_is_accepted(self, db_session):
        engine = DiscountEngine(db_session)
        valid_from, valid_until = date_range()
        code = f"valid{uuid4().hex[:8]}"
        await engine.create(code=code, discount_type=DiscountType.PERCENTAGE.value,
                             value=10, valid_from=valid_from, valid_until=valid_until)

        result = await engine.validate_discount_code(code)
        assert result["is_valid"] is True
        assert result["discount"].code == code.upper()

    async def test_unknown_code_is_rejected(self, db_session):
        engine = DiscountEngine(db_session)
        result = await engine.validate_discount_code(f"nope{uuid4().hex[:8]}")
        assert result["is_valid"] is False
        assert result["error_message"] == "Invalid discount code"

    async def test_not_yet_active_code_is_rejected(self, db_session):
        engine = DiscountEngine(db_session)
        now = datetime.now(timezone.utc)
        code = f"future{uuid4().hex[:8]}"
        await engine.create(code=code, discount_type=DiscountType.PERCENTAGE.value, value=10,
                             valid_from=now + timedelta(days=1), valid_until=now + timedelta(days=10))

        result = await engine.validate_discount_code(code)
        assert result["is_valid"] is False
        assert "not yet active" in result["error_message"]

    async def test_expired_code_is_rejected(self, db_session):
        engine = DiscountEngine(db_session)
        now = datetime.now(timezone.utc)
        code = f"expired{uuid4().hex[:8]}"
        await engine.create(code=code, discount_type=DiscountType.PERCENTAGE.value, value=10,
                             valid_from=now - timedelta(days=10), valid_until=now - timedelta(days=1))

        result = await engine.validate_discount_code(code)
        assert result["is_valid"] is False
        assert "expired" in result["error_message"]

    async def test_usage_limit_reached_is_rejected(self, db_session):
        engine = DiscountEngine(db_session)
        valid_from, valid_until = date_range()
        code = f"used{uuid4().hex[:8]}"
        discount = await engine.create(code=code, discount_type=DiscountType.PERCENTAGE.value, value=10,
                                        valid_from=valid_from, valid_until=valid_until, usage_limit=1)
        discount.used_count = 1
        await db_session.commit()

        result = await engine.validate_discount_code(code)
        assert result["is_valid"] is False
        assert "usage limit" in result["error_message"]

    async def test_below_minimum_amount_is_rejected(self, db_session):
        engine = DiscountEngine(db_session)
        valid_from, valid_until = date_range()
        code = f"minamt{uuid4().hex[:8]}"
        await engine.create(code=code, discount_type=DiscountType.PERCENTAGE.value, value=10,
                             valid_from=valid_from, valid_until=valid_until, minimum_amount=100)

        result = await engine.validate_discount_code(code, subtotal=Decimal("50.00"))
        assert result["is_valid"] is False
        assert "Minimum order amount" in result["error_message"]

    async def test_at_or_above_minimum_amount_is_accepted(self, db_session):
        engine = DiscountEngine(db_session)
        valid_from, valid_until = date_range()
        code = f"minok{uuid4().hex[:8]}"
        await engine.create(code=code, discount_type=DiscountType.PERCENTAGE.value, value=10,
                             valid_from=valid_from, valid_until=valid_until, minimum_amount=100)

        result = await engine.validate_discount_code(code, subtotal=Decimal("150.00"))
        assert result["is_valid"] is True


class TestSelectOptimalDiscount:

    async def test_no_discounts_returns_none_pair(self, db_session):
        engine = DiscountEngine(db_session)
        discount, calculation = await engine.select_optimal_discount([], subtotal=Decimal("100.00"))
        assert discount is None
        assert calculation is None

    async def test_selects_the_discount_with_greatest_savings(self, db_session):
        engine = DiscountEngine(db_session)
        valid_from, valid_until = date_range()
        small = await engine.create(code=f"small{uuid4().hex[:8]}", discount_type=DiscountType.FIXED_AMOUNT.value,
                                     value=5, valid_from=valid_from, valid_until=valid_until)
        big = await engine.create(code=f"big{uuid4().hex[:8]}", discount_type=DiscountType.FIXED_AMOUNT.value,
                                   value=20, valid_from=valid_from, valid_until=valid_until)

        best, calculation = await engine.select_optimal_discount([small, big], subtotal=Decimal("100.00"))
        assert best.id == big.id
        assert calculation["discount_amount"] == Decimal("20")


class TestGetApplicableDiscounts:

    async def test_returns_only_active_unexpired_within_budget_discounts(self, db_session):
        engine = DiscountEngine(db_session)
        valid_from, valid_until = date_range()
        applicable = await engine.create(
            code=f"appl{uuid4().hex[:8]}", discount_type=DiscountType.PERCENTAGE.value, value=10,
            valid_from=valid_from, valid_until=valid_until, minimum_amount=10,
        )
        too_expensive = await engine.create(
            code=f"toobig{uuid4().hex[:8]}", discount_type=DiscountType.PERCENTAGE.value, value=10,
            valid_from=valid_from, valid_until=valid_until, minimum_amount=1000,
        )

        results = await engine.get_applicable_discounts(subtotal=Decimal("50.00"))
        ids = [d.id for d in results]
        assert applicable.id in ids
        assert too_expensive.id not in ids


class TestList:

    async def test_lists_with_pagination_envelope(self, db_session):
        engine = DiscountEngine(db_session)
        valid_from, valid_until = date_range()
        await engine.create(code=f"list{uuid4().hex[:8]}", discount_type=DiscountType.PERCENTAGE.value,
                             value=5, valid_from=valid_from, valid_until=valid_until)

        result = await engine.list(page=1, limit=5)
        assert "items" in result
        assert result["page"] == 1
        assert result["limit"] == 5
        assert result["total"] >= 1

    async def test_filters_by_is_active(self, db_session):
        engine = DiscountEngine(db_session)
        valid_from, valid_until = date_range()
        code = f"inact{uuid4().hex[:8]}"
        discount = await engine.create(code=code, discount_type=DiscountType.PERCENTAGE.value,
                                        value=5, valid_from=valid_from, valid_until=valid_until)
        discount.is_active = False
        await db_session.commit()

        result = await engine.list(is_active=False)
        assert any(d.code == code.upper() for d in result["items"])


class TestRemoveExpiredDiscounts:

    async def test_no_expired_discounts_returns_zero_counts(self, db_session):
        engine = DiscountEngine(db_session)
        # Isolated from other tests' data by only asserting shape, not exact zero.
        result = await engine.remove_expired_discounts()
        assert "expired_discounts_count" in result
        assert "affected_subscriptions" in result

    async def test_deactivates_expired_discounts_without_crashing(self, db_session, mocker):
        """Regression test: this used to always raise AttributeError
        (select(...).delete() isn't valid SQLAlchemy) whenever there was an
        actual expired discount to clean up."""
        mocker.patch("services.commerce.discounts.send_email_by_type", return_value=None)
        engine = DiscountEngine(db_session)
        now = datetime.now(timezone.utc)
        code = f"stale{uuid4().hex[:8]}"
        discount = await engine.create(
            code=code, discount_type=DiscountType.PERCENTAGE.value, value=10,
            valid_from=now - timedelta(days=10), valid_until=now + timedelta(days=10),
        )
        # Force it into an expired state after creation (valid_until must be > valid_from to create).
        discount.valid_until = now - timedelta(days=1)
        await db_session.commit()

        result = await engine.remove_expired_discounts()

        assert result["expired_discounts_count"] >= 1
        assert code.upper() in result["expired_codes"]
        await db_session.refresh(discount)
        assert discount.is_active is False
