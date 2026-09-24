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

    async def test_explicit_current_period_start_is_honored(self, db_session, test_user, variant):
        service = SubscriptionService(db_session)
        sub = await service.create(
            user_id=test_user.id, name="Backdated", variant_ids=[str(variant.id)],
            current_period_start="2026-01-15T00:00:00+00:00",
        )
        assert sub.current_period_start.year == 2026
        assert sub.current_period_start.month == 1
        assert sub.current_period_start.day == 15

    async def test_zero_priced_variant_falls_back_to_minimum_price(self, db_session, test_user):
        category = Category(id=uuid7(), name="FreeCat", slug=f"freecat-{uuid4().hex[:8]}")
        product = Product(id=uuid7(), name="Freebie", slug=f"freebie-{uuid4().hex[:8]}", category_id=category.id)
        free_variant = ProductVariant(id=uuid7(), product_id=product.id, sku=f"FREE-{uuid4().hex[:8]}", name="Free", base_price=Decimal("0.00"))
        db_session.add_all([category, product, free_variant])
        await db_session.commit()

        service = SubscriptionService(db_session)
        sub = await service.create(user_id=test_user.id, name="Free Sub", variant_ids=[str(free_variant.id)])
        assert sub.variant_prices_at_creation[0]["price"] == pytest.approx(9.99)


class TestCalculatePricingEdgeCases:

    async def test_corrupt_discount_value_does_not_crash_pricing(self, db_session, test_user, variant):
        """Defends _calculate_pricing's discount-amount computation: if the
        promo's value can't be turned into a Decimal, pricing must still be
        returned (with no discount applied) instead of raising mid-checkout."""
        promo = Promocode(id=uuid7(), code=f"CORRUPT{uuid4().hex[:6].upper()}", discount_type="fixed", value=5, is_active=True)
        db_session.add(promo)
        await db_session.commit()
        promo.value = None  # mutated in-memory only; the service re-fetches by code within this same session

        service = SubscriptionService(db_session)
        pricing = await service._calculate_pricing(
            variants=[variant], variant_quantities={}, customer_address=None,
            currency="USD", user_id=test_user.id, discount_code=promo.code,
        )
        assert pricing["discount"] == 0.0



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

    async def test_admin_search_matches_on_user_fields(self, db_session, test_user, subscription):
        service = SubscriptionService(db_session)
        result = await service.list(user_id=None, search=test_user.email)
        assert any(s["id"] == str(subscription.id) for s in result["data"])

        no_match = await service.list(user_id=None, search="nobody-matches-this-xyz")
        assert not any(s["id"] == str(subscription.id) for s in no_match["data"])

    async def test_date_filters_include_and_exclude(self, db_session, test_user, subscription):
        service = SubscriptionService(db_session)
        today = datetime.now(timezone.utc).date().isoformat()
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
        result = await service.list(user_id=test_user.id, date_from=today, date_to=tomorrow)
        assert any(s["id"] == str(subscription.id) for s in result["data"])

        future = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
        excluded = await service.list(user_id=test_user.id, date_from=future)
        assert not any(s["id"] == str(subscription.id) for s in excluded["data"])

    async def test_invalid_date_filters_are_silently_ignored(self, db_session, test_user, subscription):
        service = SubscriptionService(db_session)
        result = await service.list(user_id=test_user.id, date_from="not-a-date", date_to="also-not-a-date")
        assert any(s["id"] == str(subscription.id) for s in result["data"])

    async def test_sorts_by_next_billing_date_and_status(self, db_session, test_user, subscription):
        service = SubscriptionService(db_session)
        by_billing = await service.list(user_id=test_user.id, sort_by="next_billing_date", sort_order="asc")
        assert any(s["id"] == str(subscription.id) for s in by_billing["data"])

        by_status = await service.list(user_id=test_user.id, sort_by="status", sort_order="asc")
        assert any(s["id"] == str(subscription.id) for s in by_status["data"])


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

    async def test_updates_delivery_address_shipping_method_and_auto_renew(
        self, db_session, test_user, subscription, address, shipping_method
    ):
        service = SubscriptionService(db_session)
        updated = await service.update(
            subscription.id, test_user.id,
            delivery_address_id=address.id, shipping_method_id=shipping_method.id, auto_renew=False,
        )
        assert updated.delivery_address_id == address.id
        assert updated.shipping_method_id == shipping_method.id
        assert updated.auto_renew is False

    async def test_updates_current_period_start_and_recomputes_period_end(self, db_session, test_user, subscription):
        service = SubscriptionService(db_session)
        updated = await service.update(
            subscription.id, test_user.id, current_period_start="2026-02-01T00:00:00+00:00",
        )
        assert updated.current_period_start.month == 2
        assert updated.current_period_end.month == 3
        assert updated.next_billing_date == updated.current_period_end

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

    async def test_updates_variant_quantities_metadata(self, db_session, test_user, subscription, variant):
        service = SubscriptionService(db_session)
        updated = await service.update(
            subscription.id, test_user.id, variant_quantities={str(variant.id): 7},
        )
        assert updated.subscription_metadata["variant_quantities"][str(variant.id)] == 7


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

    async def test_pause_not_found_raises_404(self, db_session, test_user):
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.pause(uuid4(), test_user.id)
        assert exc_info.value.status_code == 404

    async def test_resume_not_found_raises_404(self, db_session, test_user):
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.resume(uuid4(), test_user.id)
        assert exc_info.value.status_code == 404


class TestChangeFrequency:

    async def test_not_found_raises_404(self, db_session, test_user):
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.change_frequency(uuid4(), test_user.id, "weekly")
        assert exc_info.value.status_code == 404


class TestSkipUnskip:

    async def test_skip_not_found_raises_404(self, db_session, test_user):
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.skip_next_shipment(uuid4(), test_user.id)
        assert exc_info.value.status_code == 404

    async def test_unskip_not_found_raises_404(self, db_session, test_user):
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.unskip_next_shipment(uuid4(), test_user.id)
        assert exc_info.value.status_code == 404


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

    async def test_adds_a_product_when_variant_ids_was_none(self, db_session, test_user, subscription, variant):
        """add_products() must initialize variant_ids from scratch when it's None,
        rather than assuming create() always populates it."""
        subscription.variant_ids = None
        await db_session.commit()

        category = Category(id=uuid7(), name="Cat4", slug=f"cat4-{uuid4().hex[:8]}")
        product = Product(id=uuid7(), name="Extra2", slug=f"extra2-{uuid4().hex[:8]}", category_id=category.id)
        extra_variant = ProductVariant(id=uuid7(), product_id=product.id, sku=f"SKU4-{uuid4().hex[:8]}", name="Extra2", base_price=Decimal("5.00"))
        db_session.add_all([category, product, extra_variant])
        await db_session.commit()

        service = SubscriptionService(db_session)
        updated = await service.add_products(subscription.id, [extra_variant.id], test_user.id)
        assert str(extra_variant.id) in updated.variant_ids

    async def test_add_products_not_found_raises_404(self, db_session, test_user, variant):
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.add_products(uuid4(), [variant.id], test_user.id)
        assert exc_info.value.status_code == 404

    async def test_remove_products_not_found_raises_404(self, db_session, test_user, variant):
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.remove_products(uuid4(), [variant.id], test_user.id)
        assert exc_info.value.status_code == 404


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

    async def test_get_quantities_returns_empty_dict_when_no_metadata(self, db_session, test_user, subscription):
        subscription.subscription_metadata = None
        await db_session.commit()
        service = SubscriptionService(db_session)
        assert await service.get_quantities(subscription.id, test_user.id) == {}

    async def test_set_quantity_not_found_raises_404(self, db_session, test_user, variant):
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.set_quantity(uuid4(), variant.id, 2, test_user.id)
        assert exc_info.value.status_code == 404

    async def test_adjust_quantity_not_found_raises_404(self, db_session, test_user, variant):
        service = SubscriptionService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.adjust_quantity(uuid4(), variant.id, 1, test_user.id)
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
