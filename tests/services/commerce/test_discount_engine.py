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
from sqlalchemy import text
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timedelta, timezone

from core.utils.uuid_utils import uuid7
from services.commerce.discounts import DiscountEngine
from models.commerce.discounts import DiscountType, SubscriptionDiscount
from models.commerce.subscriptions import Subscription, SubscriptionStatus


def date_range(days_valid=30):
    now = datetime.now(timezone.utc)
    return now - timedelta(days=1), now + timedelta(days=days_valid)


async def make_subscription(db_session, user_id, **overrides) -> Subscription:
    fields = {
        "id": uuid7(),
        "user_id": user_id,
        "name": "Discount Engine Test Subscription",
        "status": SubscriptionStatus.ACTIVE.value,
        "variant_ids": [],
    }
    fields.update(overrides)
    subscription = Subscription(**fields)
    db_session.add(subscription)
    await db_session.commit()
    await db_session.refresh(subscription)
    return subscription


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

    async def test_duplicate_code_raises_and_rolls_back(self, db_session):
        engine = DiscountEngine(db_session)
        valid_from, valid_until = date_range()
        code = f"dup{uuid4().hex[:8]}"
        await engine.create(code=code, discount_type=DiscountType.PERCENTAGE.value,
                             value=10, valid_from=valid_from, valid_until=valid_until)

        with pytest.raises(Exception):
            await engine.create(code=code, discount_type=DiscountType.PERCENTAGE.value,
                                 value=20, valid_from=valid_from, valid_until=valid_until)

        # Session must still be usable after the rollback in the except block.
        result = await db_session.execute(text("SELECT 1"))
        assert result.scalar() == 1


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

    async def test_already_applied_to_subscription_is_rejected(self, db_session, test_user):
        engine = DiscountEngine(db_session)
        valid_from, valid_until = date_range()
        code = f"dupe{uuid4().hex[:8]}"
        discount = await engine.create(code=code, discount_type=DiscountType.PERCENTAGE.value, value=10,
                                        valid_from=valid_from, valid_until=valid_until)
        subscription = await make_subscription(db_session, test_user.id)
        db_session.add(SubscriptionDiscount(
            id=uuid7(), subscription_id=subscription.id, discount_id=discount.id,
            discount_amount=Decimal("10.00"),
        ))
        await db_session.commit()

        result = await engine.validate_discount_code(code, subscription_id=str(subscription.id))
        assert result["is_valid"] is False
        assert "already applied" in result["error_message"]

    async def test_db_error_is_caught_and_returns_generic_message(self, db_session):
        """A malformed subscription_id (not a valid UUID) blows up the
        SubscriptionDiscount lookup at the DB level rather than at the Python
        level - this must be caught, not surfaced as a raw 500."""
        engine = DiscountEngine(db_session)
        valid_from, valid_until = date_range()
        code = f"dberr{uuid4().hex[:8]}"
        await engine.create(code=code, discount_type=DiscountType.PERCENTAGE.value, value=10,
                             valid_from=valid_from, valid_until=valid_until)

        result = await engine.validate_discount_code(code, subscription_id="not-a-valid-uuid")
        assert result["is_valid"] is False
        assert result["error_message"] == "Error validating discount code"


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

    async def test_no_discount_offers_any_savings_returns_none_pair(self, db_session):
        engine = DiscountEngine(db_session)
        valid_from, valid_until = date_range()
        zero_value = await engine.create(
            code=f"zero{uuid4().hex[:8]}", discount_type=DiscountType.FIXED_AMOUNT.value,
            value=0, valid_from=valid_from, valid_until=valid_until,
        )
        best, calculation = await engine.select_optimal_discount([zero_value], subtotal=Decimal("100.00"))
        assert best is None
        assert calculation is None

    async def test_unexpected_error_during_selection_is_handled(self, db_session, mocker):
        """calculate_discount_amount() documents that it never raises, but the
        surrounding loop still needs a safety net for anything unforeseen -
        verified here by forcing it to fail."""
        engine = DiscountEngine(db_session)
        valid_from, valid_until = date_range()
        discount = await engine.create(
            code=f"boom{uuid4().hex[:8]}", discount_type=DiscountType.FIXED_AMOUNT.value,
            value=5, valid_from=valid_from, valid_until=valid_until,
        )
        mocker.patch.object(DiscountEngine, "calculate_discount_amount", side_effect=Exception("simulated failure"))

        best, calculation = await engine.select_optimal_discount([discount], subtotal=Decimal("100.00"))
        assert best is None
        assert calculation is None


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

    async def test_db_error_returns_empty_list_instead_of_raising(self, db_session, mocker):
        engine = DiscountEngine(db_session)
        mocker.patch.object(db_session, "execute", side_effect=Exception("simulated query failure"))
        results = await engine.get_applicable_discounts(subtotal=Decimal("50.00"))
        assert results == []


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

    async def test_db_error_returns_empty_result_shape(self, db_session, mocker):
        engine = DiscountEngine(db_session)
        mocker.patch.object(db_session, "execute", side_effect=Exception("simulated query failure"))
        result = await engine.list(page=2, limit=5)
        assert result == {"items": [], "total": 0, "page": 2, "limit": 5, "pages": 0}


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

    async def test_notifies_owners_of_affected_subscriptions(self, db_session, test_user, mocker):
        """When an expired discount is actually applied to a subscription, the
        owner's email is looked up and notified - the zero-affected-subscriptions
        path above never exercises this branch at all."""
        send_mock = mocker.patch("services.commerce.discounts.send_email_by_type", return_value=None)
        engine = DiscountEngine(db_session)
        now = datetime.now(timezone.utc)
        code = f"notify{uuid4().hex[:8]}"
        discount = await engine.create(
            code=code, discount_type=DiscountType.PERCENTAGE.value, value=10,
            valid_from=now - timedelta(days=10), valid_until=now + timedelta(days=10),
        )
        subscription = await make_subscription(db_session, test_user.id)
        db_session.add(SubscriptionDiscount(
            id=uuid7(), subscription_id=subscription.id, discount_id=discount.id,
            discount_amount=Decimal("10.00"),
        ))
        discount.valid_until = now - timedelta(days=1)
        await db_session.commit()

        result = await engine.remove_expired_discounts()

        assert result["affected_subscriptions"] >= 1
        assert result["notifications_sent"] >= 1
        send_mock.assert_any_call(
            to_email=test_user.email, mail_type="discount_expired", context={"company_name": "Banwee"}
        )

    async def test_notification_failure_is_swallowed_per_recipient(self, db_session, test_user, mocker):
        """A single failed email send must not prevent the discount cleanup
        itself from being reported as successful."""
        mocker.patch("services.commerce.discounts.send_email_by_type", side_effect=Exception("smtp down"))
        engine = DiscountEngine(db_session)
        now = datetime.now(timezone.utc)
        code = f"failmail{uuid4().hex[:8]}"
        discount = await engine.create(
            code=code, discount_type=DiscountType.PERCENTAGE.value, value=10,
            valid_from=now - timedelta(days=10), valid_until=now + timedelta(days=10),
        )
        subscription = await make_subscription(db_session, test_user.id)
        db_session.add(SubscriptionDiscount(
            id=uuid7(), subscription_id=subscription.id, discount_id=discount.id,
            discount_amount=Decimal("10.00"),
        ))
        discount.valid_until = now - timedelta(days=1)
        await db_session.commit()

        result = await engine.remove_expired_discounts()

        assert result["expired_discounts_count"] >= 1
        assert result["notifications_sent"] == 0

    async def test_db_error_is_caught_and_rolled_back(self, db_session, mocker):
        engine = DiscountEngine(db_session)
        now = datetime.now(timezone.utc)
        code = f"dberr{uuid4().hex[:8]}"
        discount = await engine.create(
            code=code, discount_type=DiscountType.PERCENTAGE.value, value=10,
            valid_from=now - timedelta(days=10), valid_until=now + timedelta(days=10),
        )
        discount.valid_until = now - timedelta(days=1)
        await db_session.commit()

        mocker.patch.object(db_session, "commit", side_effect=Exception("simulated commit failure"))
        rollback_spy = mocker.spy(db_session, "rollback")

        result = await engine.remove_expired_discounts()

        assert result["expired_discounts_count"] == 0
        assert "error" in result
        rollback_spy.assert_called_once()
