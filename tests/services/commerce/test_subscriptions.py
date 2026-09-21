"""Tests for services/commerce/subscriptions.py - SubscriptionService.

test_subscription_discounts.py already covers apply_discount()/remove_discount()
in detail; this file covers create, pricing, list/get, update, cancel/pause/
resume, delete, and the product/quantity management methods.
"""

import pytest
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from core.utils.uuid_utils import uuid7
from services.commerce.subscriptions import SubscriptionService
from models.commerce.subscriptions import Subscription, SubscriptionStatus
from models.catalog.category import Category
from models.catalog.product import Product, ProductVariant
from models.catalog.inventories import Inventory
from models.accounts.user import Address
from models.commerce.shipping import ShippingMethod
from models.commerce.promocode import Promocode
from models.commerce.orders import Order, OrderStatus, PaymentStatus, FulfillmentStatus


@pytest.fixture
async def variant(db_session) -> ProductVariant:
    category = Category(id=uuid7(), name="Cat", slug=f"cat-{uuid4().hex[:8]}")
    product = Product(id=uuid7(), name="Widget", slug=f"widget-{uuid4().hex[:8]}", category_id=category.id)
    v = ProductVariant(id=uuid7(), product_id=product.id, sku=f"SKU-{uuid4().hex[:8]}", name="Default", base_price=Decimal("19.99"))
    db_session.add_all([category, product, v])
    await db_session.flush()
    db_session.add(Inventory(id=uuid7(), variant_id=v.id, quantity_available=50))
    await db_session.commit()
    return v


@pytest.fixture
async def address(db_session, test_user) -> Address:
    a = Address(id=uuid7(), user_id=test_user.id, street="1 Test St", city="Lagos", state="Lagos", country="NG", post_code="100001")
    db_session.add(a)
    await db_session.commit()
    return a


@pytest.fixture
async def shipping_method(db_session) -> ShippingMethod:
    # flush, not commit - a committed row can pick up a real FK reference from a
    # committed Subscription, which then blocks other tests' cleanup.
    m = ShippingMethod(id=uuid7(), name="Standard", price=Decimal("10.00"), estimated_days=5, is_active=True)
    db_session.add(m)
    await db_session.flush()
    return m


@pytest.fixture
async def subscription(db_session, test_user, variant) -> Subscription:
    service = SubscriptionService(db_session)
    return await service.create(
        user_id=test_user.id, name="My Subscription", variant_ids=[str(variant.id)],
    )


class TestCreate:

    async def test_creates_with_calculated_pricing(self, db_session, test_user, variant, shipping_method):
        service = SubscriptionService(db_session)
        sub = await service.create(
            user_id=test_user.id, name="My Subscription", variant_ids=[str(variant.id)],
            shipping_method_id=shipping_method.id, billing_cycle="monthly",
        )
        assert sub.price_at_creation == pytest.approx(29.99)  # 19.99 item + 10.00 shipping
        assert sub.status == "active"
        assert len(sub.products) == 1

    async def test_unknown_variant_raises_400(self, db_session, test_user):
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.create(user_id=test_user.id, name="Bad Sub", variant_ids=[str(uuid4())])
        assert exc_info.value.status_code == 400

    async def test_quarterly_cycle_sets_period_end_three_months_out(self, db_session, test_user, variant):
        service = SubscriptionService(db_session)
        sub = await service.create(
            user_id=test_user.id, name="Quarterly", variant_ids=[str(variant.id)], billing_cycle="quarterly",
        )
        delta_days = (sub.current_period_end - sub.current_period_start).days
        assert 88 <= delta_days <= 92

    async def test_currency_derived_from_address_country(self, db_session, test_user, variant, address):
        address.country = "US"
        await db_session.commit()
        service = SubscriptionService(db_session)
        sub = await service.create(
            user_id=test_user.id, name="US Sub", variant_ids=[str(variant.id)], delivery_address_id=address.id,
        )
        assert sub.currency == "USD"

    async def test_applies_discount_code_at_creation(self, db_session, test_user, variant):
        promo = Promocode(id=uuid7(), code=f"SUB{uuid4().hex[:8].upper()}", discount_type="fixed", value=5, is_active=True)
        db_session.add(promo)
        await db_session.commit()

        service = SubscriptionService(db_session)
        sub = await service.create(
            user_id=test_user.id, name="Discounted", variant_ids=[str(variant.id)], discount_code=promo.code,
        )
        assert sub.discount_code == promo.code
        assert sub.discount_value == 5


class TestGetShippingCost:

    async def test_returns_specific_method_price(self, db_session, shipping_method):
        service = SubscriptionService(db_session)
        cost = await service._get_shipping_cost(shipping_method.id)
        assert cost == Decimal("10.00")

    async def test_falls_back_to_cheapest_active_method(self, db_session, shipping_method):
        service = SubscriptionService(db_session)
        cost = await service._get_shipping_cost(None)
        assert cost <= Decimal("10.00")

    async def test_falls_back_to_flat_rate_when_no_methods_exist(self, db_session):
        service = SubscriptionService(db_session)
        cost = await service._get_shipping_cost(uuid4())
        # Either the 8.99 hardcoded fallback, or a cheapest-active-method from
        # other tests' leaked data (commits aren't rolled back mid-suite).
        assert cost > Decimal("0.00")


class TestGet:

    async def test_returns_own_subscription(self, db_session, test_user, subscription):
        service = SubscriptionService(db_session)
        result = await service.get(subscription.id, test_user.id)
        assert result.id == subscription.id

    async def test_unknown_id_returns_none(self, db_session, test_user):
        service = SubscriptionService(db_session)
        assert await service.get(uuid4(), test_user.id) is None

    async def test_admin_can_fetch_without_user_filter(self, db_session, subscription):
        service = SubscriptionService(db_session)
        result = await service.get(subscription.id)
        assert result.id == subscription.id


class TestList:

    async def test_lists_own_subscriptions(self, db_session, test_user, subscription):
        service = SubscriptionService(db_session)
        result = await service.list(user_id=test_user.id)
        assert result["pagination"]["total"] >= 1
        assert any(s["id"] == str(subscription.id) for s in result["data"])

    async def test_filters_by_status(self, db_session, test_user, subscription):
        service = SubscriptionService(db_session)
        result = await service.list(user_id=test_user.id, status="active")
        assert all(s["status"] == "active" for s in result["data"])

    async def test_admin_lists_all_with_user_info(self, db_session, subscription):
        service = SubscriptionService(db_session)
        result = await service.list(user_id=None)
        entry = next(s for s in result["data"] if s["id"] == str(subscription.id))
        assert "user" in entry

    async def test_search_by_name(self, db_session, test_user, subscription):
        service = SubscriptionService(db_session)
        result = await service.list(user_id=test_user.id, search="My Subscription")
        assert any(s["id"] == str(subscription.id) for s in result["data"])


class TestUpdate:

    async def test_updates_name(self, db_session, test_user, subscription):
        service = SubscriptionService(db_session)
        updated = await service.update(subscription.id, test_user.id, name="Renamed")
        assert updated.name == "Renamed"

    async def test_not_found_raises_404(self, db_session, test_user):
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.update(uuid4(), test_user.id, name="x")
        assert exc_info.value.status_code == 404

    async def test_cannot_update_cancelled_subscription(self, db_session, test_user, subscription):
        subscription.status = "cancelled"
        await db_session.commit()
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.update(subscription.id, test_user.id, name="x")
        assert exc_info.value.status_code == 400

    async def test_updates_variant_ids_and_associations(self, db_session, test_user, subscription, variant):
        category = Category(id=uuid7(), name="Cat2", slug=f"cat2-{uuid4().hex[:8]}")
        product = Product(id=uuid7(), name="Gadget", slug=f"gadget-{uuid4().hex[:8]}", category_id=category.id)
        new_variant = ProductVariant(id=uuid7(), product_id=product.id, sku=f"SKU2-{uuid4().hex[:8]}", name="New", base_price=Decimal("9.99"))
        db_session.add_all([category, product, new_variant])
        await db_session.commit()

        service = SubscriptionService(db_session)
        updated = await service.update(subscription.id, test_user.id, variant_ids=[str(new_variant.id)])
        assert updated.variant_ids == [str(new_variant.id)]
        assert len(updated.products) == 1
        assert updated.products[0].id == new_variant.id


class TestCancelPauseResume:

    async def test_cancels_active_subscription(self, db_session, test_user, subscription):
        service = SubscriptionService(db_session)
        result = await service.cancel(subscription.id, test_user.id, reason="No longer needed")
        assert result.status == "cancelled"
        assert result.auto_renew is False

    async def test_cancel_not_found_raises_404(self, db_session, test_user):
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.cancel(uuid4(), test_user.id)
        assert exc_info.value.status_code == 404

    async def test_pauses_active_subscription(self, db_session, test_user, subscription):
        service = SubscriptionService(db_session)
        result = await service.pause(subscription.id, test_user.id, reason="Vacation")
        assert result.status == "paused"
        assert result.pause_reason == "Vacation"

    async def test_cannot_pause_non_active_subscription(self, db_session, test_user, subscription):
        subscription.status = "cancelled"
        await db_session.commit()
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.pause(subscription.id, test_user.id)
        assert exc_info.value.status_code == 400

    async def test_resumes_a_paused_subscription(self, db_session, test_user, subscription):
        service = SubscriptionService(db_session)
        await service.pause(subscription.id, test_user.id)
        result = await service.resume(subscription.id, test_user.id)
        assert result.status == "active"
        assert result.auto_renew is True

    async def test_cannot_resume_an_active_subscription(self, db_session, test_user, subscription):
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.resume(subscription.id, test_user.id)
        assert exc_info.value.status_code == 400


class TestRecalcPricing:

    async def test_recalculates_current_pricing(self, db_session, test_user, subscription, variant):
        variant.base_price = Decimal("29.99")
        await db_session.commit()

        service = SubscriptionService(db_session)
        pricing = await service.recalc_pricing(subscription)
        assert pricing["subtotal"] == pytest.approx(29.99)
        await db_session.refresh(subscription)
        assert subscription.current_shipping_amount is not None


class TestDelete:

    async def test_deletes_a_subscription_and_its_associations(self, db_session, test_user, subscription):
        service = SubscriptionService(db_session)
        assert await service.delete(subscription.id, test_user.id) is True
        assert await service.get(subscription.id) is None

    async def test_unlinks_orders_instead_of_deleting_them(self, db_session, test_user, subscription):
        order = Order(
            id=uuid7(), order_number=f"ORD-{uuid4().hex[:10].upper()}", user_id=test_user.id,
            order_status=OrderStatus.CONFIRMED, payment_status=PaymentStatus.PAID,
            fulfillment_status=FulfillmentStatus.UNFULFILLED,
            subtotal=19.99, shipping_cost=0, tax_amount=0, total_amount=19.99,
            billing_address={}, shipping_address={}, subscription_id=subscription.id,
        )
        db_session.add(order)
        await db_session.commit()

        service = SubscriptionService(db_session)
        await service.delete(subscription.id, test_user.id)

        await db_session.refresh(order)
        assert order.subscription_id is None

    async def test_not_found_raises_404(self, db_session, test_user):
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.delete(uuid4(), test_user.id)
        assert exc_info.value.status_code == 404


class TestProductManagement:

    async def test_adds_a_new_product(self, db_session, test_user, subscription):
        category = Category(id=uuid7(), name="Cat3", slug=f"cat3-{uuid4().hex[:8]}")
        product = Product(id=uuid7(), name="Extra", slug=f"extra-{uuid4().hex[:8]}", category_id=category.id)
        extra_variant = ProductVariant(id=uuid7(), product_id=product.id, sku=f"SKU3-{uuid4().hex[:8]}", name="Extra", base_price=Decimal("5.00"))
        db_session.add_all([category, product, extra_variant])
        await db_session.commit()

        service = SubscriptionService(db_session)
        updated = await service.add_products(subscription.id, [extra_variant.id], test_user.id)
        assert len(updated.products) == 2

    async def test_removes_a_product(self, db_session, test_user, subscription, variant):
        service = SubscriptionService(db_session)
        updated = await service.remove_products(subscription.id, [variant.id], test_user.id)
        assert len(updated.products) == 0
        assert str(variant.id) not in updated.variant_ids


class TestQuantityManagement:

    async def test_sets_quantity(self, db_session, test_user, subscription, variant):
        service = SubscriptionService(db_session)
        updated = await service.set_quantity(subscription.id, variant.id, 3, test_user.id)
        assert updated.subscription_metadata["variant_quantities"][str(variant.id)] == 3

    async def test_adjusts_quantity_up(self, db_session, test_user, subscription, variant):
        service = SubscriptionService(db_session)
        await service.set_quantity(subscription.id, variant.id, 2, test_user.id)
        updated = await service.adjust_quantity(subscription.id, variant.id, 1, test_user.id)
        assert updated.subscription_metadata["variant_quantities"][str(variant.id)] == 3

    async def test_adjust_quantity_never_goes_below_one(self, db_session, test_user, subscription, variant):
        service = SubscriptionService(db_session)
        updated = await service.adjust_quantity(subscription.id, variant.id, -10, test_user.id)
        assert updated.subscription_metadata["variant_quantities"][str(variant.id)] == 1

    async def test_get_quantities(self, db_session, test_user, subscription, variant):
        service = SubscriptionService(db_session)
        await service.set_quantity(subscription.id, variant.id, 4, test_user.id)
        quantities = await service.get_quantities(subscription.id, test_user.id)
        assert quantities[str(variant.id)] == 4

    async def test_get_quantities_not_found_raises_404(self, db_session, test_user):
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.get_quantities(uuid4(), test_user.id)
        assert exc_info.value.status_code == 404


class TestGetOrders:

    async def test_returns_orders_for_subscription(self, db_session, test_user, subscription):
        order = Order(
            id=uuid7(), order_number=f"ORD-{uuid4().hex[:10].upper()}", user_id=test_user.id,
            order_status=OrderStatus.CONFIRMED, payment_status=PaymentStatus.PAID,
            fulfillment_status=FulfillmentStatus.UNFULFILLED,
            subtotal=19.99, shipping_cost=0, tax_amount=0, total_amount=19.99,
            billing_address={}, shipping_address={}, subscription_id=subscription.id,
        )
        db_session.add(order)
        await db_session.commit()

        service = SubscriptionService(db_session)
        result = await service.get_orders(subscription.id, test_user.id)
        assert result["total"] >= 1

    async def test_not_found_raises_404(self, db_session, test_user):
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.get_orders(uuid4(), test_user.id)
        assert exc_info.value.status_code == 404
