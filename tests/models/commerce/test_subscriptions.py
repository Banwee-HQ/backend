"""Tests for models/commerce/subscriptions.py."""

import pytest
from uuid import uuid4
from decimal import Decimal
from datetime import date, datetime, timezone

from core.utils.uuid_utils import uuid7
from models.commerce.subscriptions import (
    Subscription, SubscriptionProduct, SubscriptionCostHistory, SubscriptionAnalytics,
    SubscriptionStatus, BillingCycle,
)
from models.catalog.category import Category
from models.catalog.product import Product, ProductVariant
from models.catalog.inventories import Inventory


def make_subscription(**overrides) -> Subscription:
    fields = dict(
        id=uuid7(), user_id=uuid7(), name="My Subscription", status=SubscriptionStatus.ACTIVE.value,
        currency="USD", billing_cycle=BillingCycle.MONTHLY.value, auto_renew=True,
        variant_ids=[], created_at=datetime.now(timezone.utc),
    )
    fields.update(overrides)
    return Subscription(**fields)


class TestSubscriptionProduct:

    def test_is_active_when_not_removed(self):
        sp = SubscriptionProduct(id=uuid7(), subscription_id=uuid7(), product_id=uuid7(), quantity=1, unit_price=Decimal("9.99"), total_price=Decimal("9.99"))
        assert sp.is_active is True

    def test_is_inactive_when_removed(self):
        sp = SubscriptionProduct(
            id=uuid7(), subscription_id=uuid7(), product_id=uuid7(), quantity=1,
            unit_price=Decimal("9.99"), total_price=Decimal("9.99"), removed_at=datetime.now(timezone.utc),
        )
        assert sp.is_active is False

    def test_to_dict_reflects_is_active(self):
        sp = SubscriptionProduct(id=uuid7(), subscription_id=uuid7(), product_id=uuid7(), quantity=2, unit_price=Decimal("9.99"), total_price=Decimal("19.98"))
        data = sp.to_dict()
        assert data["is_active"] is True
        assert data["quantity"] == 2


class TestSubscriptionToDict:

    def test_serializes_core_fields_without_relationships(self):
        sub = make_subscription(price_at_creation=Decimal("49.98"))
        data = sub.to_dict()
        assert data["name"] == "My Subscription"
        assert data["status"] == SubscriptionStatus.ACTIVE.value
        assert data["price_at_creation"] == Decimal("49.98")
        assert data["delivery_address"] is None
        assert data["shipping_method"] is None

    def test_discount_is_none_when_no_discount_type(self):
        sub = make_subscription()
        assert sub.to_dict()["discount"] is None

    def test_discount_included_when_set(self):
        sub = make_subscription(discount_type="percentage", discount_value=Decimal("10.00"), discount_code="SAVE10")
        data = sub.to_dict()
        assert data["discount"] == {"type": "percentage", "value": Decimal("10.00"), "code": "SAVE10"}

    def test_empty_json_fields_default_to_empty_collections(self):
        sub = make_subscription()
        data = sub.to_dict()
        assert data["variant_ids"] == []
        assert data["subscription_metadata"] == {}
        assert data["variant_prices_at_creation"] == []


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


class TestSubscriptionToDictWithProducts:

    async def test_includes_product_entries(self, db_session, test_user, variant):
        sub = Subscription(
            id=uuid7(), user_id=test_user.id, name="Sub", status=SubscriptionStatus.ACTIVE.value,
            currency="USD", billing_cycle=BillingCycle.MONTHLY.value, variant_ids=[str(variant.id)],
            subscription_metadata={"variant_quantities": {str(variant.id): 3}},
        )
        db_session.add(sub)
        await db_session.flush()
        from models.commerce.subscriptions import SubscriptionProductAssociation
        db_session.add(SubscriptionProductAssociation(subscription_id=sub.id, product_variant_id=variant.id))
        await db_session.commit()

        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        result = await db_session.execute(
            select(Subscription).where(Subscription.id == sub.id).options(
                selectinload(Subscription.products).selectinload(ProductVariant.product)
            )
        )
        fresh = result.scalar_one()
        data = fresh.to_dict(include_products=True)
        assert len(data["products"]) == 1
        assert data["products"][0]["quantity"] == 3
        assert data["products"][0]["name"] == "Widget"


class TestSubscriptionCostHistoryToDict:

    def test_serializes_fields(self):
        history = SubscriptionCostHistory(
            id=uuid7(), subscription_id=uuid7(), new_cost_breakdown={"total": 49.98},
            change_reason="variant_price_change", effective_date=datetime.now(timezone.utc),
        )
        data = history.to_dict()
        assert data["change_reason"] == "variant_price_change"
        assert data["new_cost_breakdown"] == {"total": 49.98}
        assert data["changed_by"] is None


class TestSubscriptionAnalyticsToDict:

    def test_serializes_date_and_metrics(self):
        analytics = SubscriptionAnalytics(
            id=uuid7(), date=date(2026, 1, 1), total_active_subscriptions=10,
            total_revenue=Decimal("500.00"), currency="USD",
        )
        data = analytics.to_dict()
        assert data["date"] == "2026-01-01"
        assert data["total_active_subscriptions"] == 10
