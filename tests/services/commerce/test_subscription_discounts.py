"""Tests for SubscriptionService.apply_discount/remove_discount (services/commerce/subscriptions.py).

POST/DELETE /v1/subscriptions/{id}/discounts/ used to unconditionally return
501 "not yet implemented". Subscription already carries its own
discount_id/discount_type/discount_value/discount_code columns (discount_id
FKs to commerce.promocodes, not the separate, largely-dead Discount/
DiscountEngine system in services/commerce/discounts.py), and
_calculate_pricing already knows how to resolve a Promocode by code - these
tests exercise the new service methods that wire that existing logic up to
an already-created subscription instead of only at creation time.
"""

import pytest
from uuid import uuid4
from fastapi import HTTPException

from services.accounts.auth import AuthService
from services.commerce.subscriptions import SubscriptionService
from models.accounts.user import User, UserRole
from models.commerce.subscriptions import Subscription, SubscriptionStatus
from models.commerce.promocode import Promocode


async def make_user(db_session) -> User:
    auth = AuthService(db_session)
    user = User(
        id=uuid4(),
        email=f"sub_discount_{uuid4().hex[:8]}@example.com",
        firstname="Test",
        lastname="User",
        hashed_password=auth.get_password_hash("Password123!"),
        role=UserRole.CUSTOMER,
        account_status="active",
        verification_status="verified",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def make_subscription(db_session, user_id, **overrides) -> Subscription:
    fields = {
        "id": uuid4(),
        "user_id": user_id,
        "name": "Test Subscription",
        "status": SubscriptionStatus.ACTIVE.value,
        "variant_ids": [],
    }
    fields.update(overrides)
    subscription = Subscription(**fields)
    db_session.add(subscription)
    await db_session.commit()
    await db_session.refresh(subscription)
    return subscription


async def make_promocode(db_session, code=None, discount_type="percentage", value=10, **overrides) -> Promocode:
    fields = {
        "id": uuid4(),
        "code": code or f"SUB{uuid4().hex[:8].upper()}",
        "discount_type": discount_type,
        "value": value,
        "is_active": True,
    }
    fields.update(overrides)
    promo = Promocode(**fields)
    db_session.add(promo)
    await db_session.commit()
    await db_session.refresh(promo)
    return promo


class TestApplyDiscount:

    async def test_applies_a_valid_promocode(self, db_session):
        user = await make_user(db_session)
        subscription = await make_subscription(db_session, user.id)
        promo = await make_promocode(db_session)
        service = SubscriptionService(db_session)

        updated = await service.apply_discount(subscription.id, user.id, promo.code)
        assert updated.discount_id == promo.id
        assert updated.discount_code == promo.code
        assert updated.discount_type == "percentage"

    async def test_unknown_subscription_raises_404(self, db_session):
        user = await make_user(db_session)
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.apply_discount(uuid4(), user.id, "WHATEVER")
        assert exc_info.value.status_code == 404

    async def test_other_users_subscription_is_not_found(self, db_session):
        owner = await make_user(db_session)
        other = await make_user(db_session)
        subscription = await make_subscription(db_session, owner.id)
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.apply_discount(subscription.id, other.id, "WHATEVER")
        assert exc_info.value.status_code == 404

    async def test_invalid_code_is_rejected_and_leaves_subscription_unchanged(self, db_session):
        user = await make_user(db_session)
        subscription = await make_subscription(db_session, user.id)
        service = SubscriptionService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.apply_discount(subscription.id, user.id, f"NOPE{uuid4().hex[:8]}")
        assert exc_info.value.status_code == 400

        await db_session.refresh(subscription)
        assert subscription.discount_id is None
        assert subscription.discount_code is None

    async def test_cancelled_subscription_is_rejected(self, db_session):
        user = await make_user(db_session)
        subscription = await make_subscription(db_session, user.id, status=SubscriptionStatus.CANCELLED.value)
        promo = await make_promocode(db_session)
        service = SubscriptionService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.apply_discount(subscription.id, user.id, promo.code)
        assert exc_info.value.status_code == 400

    async def test_paused_subscription_is_accepted(self, db_session):
        user = await make_user(db_session)
        subscription = await make_subscription(db_session, user.id, status=SubscriptionStatus.PAUSED.value)
        promo = await make_promocode(db_session)
        service = SubscriptionService(db_session)

        updated = await service.apply_discount(subscription.id, user.id, promo.code)
        assert updated.discount_id == promo.id


class TestRemoveDiscount:

    async def test_removes_the_applied_discount(self, db_session):
        user = await make_user(db_session)
        subscription = await make_subscription(db_session, user.id)
        promo = await make_promocode(db_session)
        service = SubscriptionService(db_session)
        applied = await service.apply_discount(subscription.id, user.id, promo.code)

        updated = await service.remove_discount(subscription.id, user.id, applied.discount_id)
        assert updated.discount_id is None
        assert updated.discount_code is None
        assert updated.discount_type is None
        assert updated.discount_value is None

    async def test_unknown_subscription_raises_404(self, db_session):
        user = await make_user(db_session)
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.remove_discount(uuid4(), user.id, uuid4())
        assert exc_info.value.status_code == 404

    async def test_mismatched_discount_id_raises_404(self, db_session):
        user = await make_user(db_session)
        subscription = await make_subscription(db_session, user.id)
        promo = await make_promocode(db_session)
        service = SubscriptionService(db_session)
        await service.apply_discount(subscription.id, user.id, promo.code)

        with pytest.raises(HTTPException) as exc_info:
            await service.remove_discount(subscription.id, user.id, uuid4())
        assert exc_info.value.status_code == 404
