"""Tests for services/catalog/recommendations.py - RecommendationService.

Regression coverage for a systemic bug: Product.is_active is a Python-only
property (mirrors product_status == "active"), not a real column - every
`Product.is_active == True` filter used in a SQL query silently compiled to
`WHERE false`. That broke _get_similar_products, _get_behavioral_products,
_fetch_products, and both branches of _get_fallback_recommendations, so the
entire recommendations feature never returned a single result in production
regardless of catalog data. Fixed to filter on the real
Product.product_status column; these tests verify each algorithm (and the
fallback path) can now actually find active products.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timedelta, timezone

from services.catalog.recommendations import RecommendationService
from models.catalog.product import Product, ProductVariant, ProductStatus
from models.catalog.category import Category
from models.commerce.orders import Order, OrderItem
from models.accounts.user import User, UserRole
from services.accounts.auth import AuthService


async def make_category(db_session, **overrides) -> Category:
    fields = {"id": uuid4(), "name": "Test Category", "slug": f"cat-{uuid4().hex[:8]}"}
    fields.update(overrides)
    category = Category(**fields)
    db_session.add(category)
    await db_session.commit()
    await db_session.refresh(category)
    return category


async def make_product(db_session, category_id=None, status=ProductStatus.ACTIVE, **overrides) -> Product:
    fields = {
        "id": uuid4(),
        "name": "Test Product",
        "slug": f"prod-{uuid4().hex[:8]}",
        "category_id": category_id,
        "product_status": status,
    }
    fields.update(overrides)
    product = Product(**fields)
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product


async def make_variant(db_session, product_id, base_price=50.0, **overrides) -> ProductVariant:
    fields = {
        "id": uuid4(),
        "product_id": product_id,
        "sku": f"SKU-{uuid4().hex[:10]}",
        "name": "Variant",
        "base_price": base_price,
    }
    fields.update(overrides)
    variant = ProductVariant(**fields)
    db_session.add(variant)
    await db_session.commit()
    await db_session.refresh(variant)
    return variant


async def make_user(db_session) -> User:
    auth = AuthService(db_session)
    user = User(
        id=uuid4(), email=f"reco_{uuid4().hex[:8]}@example.com", firstname="T", lastname="U",
        hashed_password=auth.get_password_hash("Password123!"), role=UserRole.CUSTOMER,
        account_status="active", verification_status="verified",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def make_order_with_items(db_session, user_id, variant_ids, **order_overrides) -> Order:
    fields = {
        "id": uuid4(),
        "order_number": f"ORD-{uuid4().hex[:10].upper()}",
        "user_id": user_id,
        "subtotal": 10.0,
        "total_amount": 10.0,
        "billing_address": {"country": "US"},
        "shipping_address": {"country": "US"},
    }
    fields.update(order_overrides)
    order = Order(**fields)
    db_session.add(order)
    await db_session.flush()

    for variant_id in variant_ids:
        db_session.add(OrderItem(
            id=uuid4(), order_id=order.id, variant_id=variant_id,
            quantity=1, price_per_unit=10.0, total_price=10.0,
        ))
    await db_session.commit()
    await db_session.refresh(order)
    return order


class TestGetSimilarProducts:

    async def test_finds_active_products_in_the_same_category_and_price_range(self, db_session):
        category = await make_category(db_session)
        source = await make_product(db_session, category_id=category.id)
        await make_variant(db_session, source.id, base_price=50.0)

        similar = await make_product(db_session, category_id=category.id)
        await make_variant(db_session, similar.id, base_price=55.0)

        service = RecommendationService(db_session)
        results = await service._get_similar_products(source, limit=10)

        assert any(pid == similar.id for pid, _ in results)

    async def test_excludes_inactive_products(self, db_session):
        category = await make_category(db_session)
        source = await make_product(db_session, category_id=category.id)
        await make_variant(db_session, source.id, base_price=50.0)

        inactive = await make_product(db_session, category_id=category.id, status=ProductStatus.INACTIVE)
        await make_variant(db_session, inactive.id, base_price=50.0)

        service = RecommendationService(db_session)
        results = await service._get_similar_products(source, limit=10)

        assert all(pid != inactive.id for pid, _ in results)

    async def test_no_variants_on_source_returns_empty(self, db_session):
        category = await make_category(db_session)
        source = await make_product(db_session, category_id=category.id)
        service = RecommendationService(db_session)
        assert await service._get_similar_products(source, limit=10) == []


class TestGetComplementaryProducts:

    async def test_finds_products_frequently_bought_together(self, db_session):
        category = await make_category(db_session)
        user = await make_user(db_session)
        main = await make_product(db_session, category_id=category.id)
        main_variant = await make_variant(db_session, main.id)
        companion = await make_product(db_session, category_id=category.id)
        companion_variant = await make_variant(db_session, companion.id)

        await make_order_with_items(db_session, user.id, [main_variant.id, companion_variant.id])

        service = RecommendationService(db_session)
        results = await service._get_complementary_products(main.id, limit=10)
        assert any(pid == companion.id for pid, _ in results)

    async def test_no_orders_returns_empty(self, db_session):
        service = RecommendationService(db_session)
        assert await service._get_complementary_products(uuid4(), limit=10) == []


class TestGetBehavioralProducts:

    async def test_finds_active_products_in_the_same_category(self, db_session):
        category = await make_category(db_session)
        source = await make_product(db_session, category_id=category.id)
        popular = await make_product(db_session, category_id=category.id)

        service = RecommendationService(db_session)
        results = await service._get_behavioral_products(source.id, limit=10)
        assert any(pid == popular.id for pid, _ in results)

    async def test_excludes_inactive_products(self, db_session):
        category = await make_category(db_session)
        source = await make_product(db_session, category_id=category.id)
        inactive = await make_product(db_session, category_id=category.id, status=ProductStatus.DRAFT)

        service = RecommendationService(db_session)
        results = await service._get_behavioral_products(source.id, limit=10)
        assert all(pid != inactive.id for pid, _ in results)


class TestFetchProducts:

    async def test_fetches_and_preserves_order(self, db_session):
        category = await make_category(db_session)
        p1 = await make_product(db_session, category_id=category.id)
        p2 = await make_product(db_session, category_id=category.id)

        service = RecommendationService(db_session)
        results = await service._fetch_products([p2.id, p1.id])
        assert [r.id for r in results] == [p2.id, p1.id]

    async def test_excludes_inactive_products(self, db_session):
        category = await make_category(db_session)
        inactive = await make_product(db_session, category_id=category.id, status=ProductStatus.INACTIVE)

        service = RecommendationService(db_session)
        results = await service._fetch_products([inactive.id])
        assert results == []

    async def test_empty_input_returns_empty(self, db_session):
        service = RecommendationService(db_session)
        assert await service._fetch_products([]) == []


class TestGetFallbackRecommendations:

    async def test_returns_active_products_in_same_category(self, db_session):
        category = await make_category(db_session)
        source = await make_product(db_session, category_id=category.id)
        other = await make_product(db_session, category_id=category.id)

        service = RecommendationService(db_session)
        results = await service._get_fallback_recommendations(source, limit=10)
        assert any(r.id == other.id for r in results)

    async def test_falls_back_to_any_active_product_when_category_is_empty(self, db_session):
        """The "any active product" fallback has no ORDER BY, so with a small
        limit and other tests' products already committed in this shared DB,
        our own product isn't guaranteed to be among the first N rows - use a
        high limit so this assertion doesn't depend on row order."""
        empty_category = await make_category(db_session)
        source = await make_product(db_session, category_id=empty_category.id)
        other_category = await make_category(db_session)
        elsewhere = await make_product(db_session, category_id=other_category.id)

        service = RecommendationService(db_session)
        results = await service._get_fallback_recommendations(source, limit=10000)
        assert any(r.id == elsewhere.id for r in results)


class TestGetSmartRecommendations:

    async def test_unknown_product_returns_empty(self, db_session):
        service = RecommendationService(db_session)
        assert await service.get_smart_recommendations(uuid4()) == []

    async def test_returns_recommendations_via_fallback_when_no_signal_data(self, db_session):
        """A brand-new product with no orders/reviews still gets recommendations
        via the category fallback, once the is_active bug no longer zeroes out
        every candidate query."""
        category = await make_category(db_session)
        source = await make_product(db_session, category_id=category.id)
        await make_variant(db_session, source.id)
        other = await make_product(db_session, category_id=category.id)

        service = RecommendationService(db_session)
        results = await service.get_smart_recommendations(source.id, limit=5)
        assert len(results) >= 1
