"""Tests for services/catalog/products.py - ProductService."""

import pytest
from uuid import UUID, uuid4
from decimal import Decimal
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select

from core.exceptions import APIException
from core.utils.uuid_utils import uuid7
from services.catalog.products import ProductService
from schemas.catalog.product import (
    Create as ProductCreate, Update as ProductUpdate, VariantUpdate, VariantCreate,
)
from models.catalog.category import Category
from models.catalog.product import Product, ProductVariant, ProductImage, ProductStatus
from models.catalog.inventories import Inventory, WarehouseLocation, StockAdjustment
from models.catalog.review import Review
from models.commerce.cart import Cart, CartItem
from models.commerce.orders import Order, OrderItem, OrderStatus, PaymentStatus, FulfillmentStatus


async def make_category(db_session, **overrides) -> Category:
    fields = {"id": uuid4(), "name": "Cat", "slug": f"cat-{uuid4().hex[:8]}"}
    fields.update(overrides)
    category = Category(**fields)
    db_session.add(category)
    await db_session.commit()
    await db_session.refresh(category)
    return category


async def make_product(db_session, category_id=None, status=ProductStatus.ACTIVE, **overrides) -> Product:
    fields = {"id": uuid4(), "name": "Widget", "slug": f"widget-{uuid4().hex[:8]}",
              "category_id": category_id, "product_status": status}
    fields.update(overrides)
    product = Product(**fields)
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product


async def make_variant(db_session, product_id, base_price=20.0, sale_price=None, is_active=True, **overrides) -> ProductVariant:
    fields = {"id": uuid4(), "product_id": product_id, "sku": f"SKU-{uuid4().hex[:10]}",
              "name": "Variant", "base_price": Decimal(str(base_price)),
              "sale_price": Decimal(str(sale_price)) if sale_price is not None else None, "is_active": is_active}
    fields.update(overrides)
    variant = ProductVariant(**fields)
    db_session.add(variant)
    await db_session.commit()
    await db_session.refresh(variant)
    return variant


async def make_inventory(db_session, variant_id, quantity_available=50) -> Inventory:
    inv = Inventory(id=uuid4(), variant_id=variant_id, quantity_available=quantity_available)
    db_session.add(inv)
    await db_session.commit()
    await db_session.refresh(inv)
    return inv


class TestList:

    async def test_only_lists_active_products(self, db_session):
        cat = await make_category(db_session)
        await make_product(db_session, category_id=cat.id, name="Active One", status=ProductStatus.ACTIVE)
        await make_product(db_session, category_id=cat.id, name="Draft One", status=ProductStatus.DRAFT)

        service = ProductService(db_session)
        result = await service.list()
        names = [p.name for p in result["data"]]
        assert "Active One" in names
        assert "Draft One" not in names

    async def test_filters_by_search_query(self, db_session):
        cat = await make_category(db_session)
        await make_product(db_session, category_id=cat.id, name="Organic Rice")
        await make_product(db_session, category_id=cat.id, name="Steel Pan")

        service = ProductService(db_session)
        result = await service.list(filters={"q": "organic"})
        names = [p.name for p in result["data"]]
        assert "Organic Rice" in names
        assert "Steel Pan" not in names

    async def test_filters_by_category_slug(self, db_session):
        cat_a = await make_category(db_session, slug="cat-a")
        cat_b = await make_category(db_session, slug="cat-b")
        await make_product(db_session, category_id=cat_a.id, name="In A")
        await make_product(db_session, category_id=cat_b.id, name="In B")

        service = ProductService(db_session)
        result = await service.list(filters={"category": "cat-a"})
        names = [p.name for p in result["data"]]
        assert "In A" in names
        assert "In B" not in names

    async def test_filters_by_price_range(self, db_session):
        cat = await make_category(db_session)
        cheap = await make_product(db_session, category_id=cat.id, name="Cheap")
        await make_variant(db_session, cheap.id, base_price=5.0)
        pricey = await make_product(db_session, category_id=cat.id, name="Pricey")
        await make_variant(db_session, pricey.id, base_price=500.0)

        service = ProductService(db_session)
        result = await service.list(filters={"min_price": 1, "max_price": 10})
        names = [p.name for p in result["data"]]
        assert "Cheap" in names
        assert "Pricey" not in names

    async def test_filters_by_availability(self, db_session):
        cat = await make_category(db_session)
        in_stock = await make_product(db_session, category_id=cat.id, name="In Stock")
        v1 = await make_variant(db_session, in_stock.id)
        await make_inventory(db_session, v1.id, quantity_available=5)
        out_of_stock = await make_product(db_session, category_id=cat.id, name="Out Of Stock")
        v2 = await make_variant(db_session, out_of_stock.id)
        await make_inventory(db_session, v2.id, quantity_available=0)

        service = ProductService(db_session)
        result = await service.list(filters={"availability": True})
        names = [p.name for p in result["data"]]
        assert "In Stock" in names
        assert "Out Of Stock" not in names

    async def test_filters_by_sale(self, db_session):
        cat = await make_category(db_session)
        on_sale = await make_product(db_session, category_id=cat.id, name="On Sale")
        await make_variant(db_session, on_sale.id, base_price=20.0, sale_price=15.0)
        full_price = await make_product(db_session, category_id=cat.id, name="Full Price")
        await make_variant(db_session, full_price.id, base_price=20.0)

        service = ProductService(db_session)
        result = await service.list(filters={"sale": True})
        names = [p.name for p in result["data"]]
        assert "On Sale" in names
        assert "Full Price" not in names

    async def test_filters_by_featured(self, db_session):
        cat = await make_category(db_session)
        await make_product(db_session, category_id=cat.id, name="Featured", is_featured=True)
        await make_product(db_session, category_id=cat.id, name="Not Featured", is_featured=False)

        service = ProductService(db_session)
        result = await service.list(filters={"is_featured": True})
        names = [p.name for p in result["data"]]
        assert "Featured" in names
        assert "Not Featured" not in names

    async def test_sorts_ascending(self, db_session):
        cat = await make_category(db_session)
        await make_product(db_session, category_id=cat.id, name="B Product")
        await make_product(db_session, category_id=cat.id, name="A Product")

        service = ProductService(db_session)
        result = await service.list(sort_by="name", sort_order="asc")
        names = [p.name for p in result["data"]]
        assert names.index("A Product") < names.index("B Product")

    async def test_pagination_totals(self, db_session):
        cat = await make_category(db_session)
        for i in range(3):
            await make_product(db_session, category_id=cat.id, name=f"Product {i}")

        service = ProductService(db_session)
        result = await service.list(page=1, limit=2)
        assert len(result["data"]) == 2
        assert result["total"] >= 3
        assert result["total_pages"] >= 2


class TestFeaturedAndPopular:

    async def test_featured_only_returns_featured_active_products(self, db_session):
        cat = await make_category(db_session)
        await make_product(db_session, category_id=cat.id, name="Featured", is_featured=True)
        await make_product(db_session, category_id=cat.id, name="Not Featured", is_featured=False)

        service = ProductService(db_session)
        result = await service.featured(limit=10)
        names = [p.name for p in result]
        assert "Featured" in names
        assert "Not Featured" not in names


class TestGet:

    async def test_get_by_id(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)

        service = ProductService(db_session)
        result = await service.get(product_id=product.id)
        assert result.id == product.id

    async def test_get_by_slug(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id, slug="my-slug")

        service = ProductService(db_session)
        result = await service.get(slug="my-slug")
        assert result.id == product.id

    async def test_get_unknown_returns_none(self, db_session):
        service = ProductService(db_session)
        result = await service.get(product_id=uuid4())
        assert result is None

    async def test_get_without_id_or_slug_raises(self, db_session):
        service = ProductService(db_session)
        with pytest.raises(ValueError):
            await service.get()


class TestVariantCrud:

    async def test_create_variant(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)

        service = ProductService(db_session)
        from schemas.catalog.product import VariantCreate
        variant = await service.create_variant(product.id, VariantCreate(
            name="Large", base_price=29.99, sale_price=24.99, stock=10
        ))
        assert variant.name == "Large"
        assert variant.stock == 10

    async def test_create_variant_unknown_product_raises_404(self, db_session):
        service = ProductService(db_session)
        from schemas.catalog.product import VariantCreate
        with pytest.raises(HTTPException) as exc_info:
            await service.create_variant(uuid4(), VariantCreate(name="Large", base_price=29.99, sale_price=24.99))
        assert exc_info.value.status_code == 404

    async def test_update_variant_stock(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)
        variant = await make_variant(db_session, product.id)
        await make_inventory(db_session, variant.id, quantity_available=5)

        service = ProductService(db_session)
        updated = await service.update_variant(variant.id, VariantUpdate(stock=99))
        assert updated.stock == 99

    async def test_update_unknown_variant_raises_404(self, db_session):
        service = ProductService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.update_variant(uuid4(), VariantUpdate(name="X"))
        assert exc_info.value.status_code == 404

    async def test_delete_variant(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)
        await make_variant(db_session, product.id)
        variant = await make_variant(db_session, product.id)

        service = ProductService(db_session)
        assert await service.delete_variant(variant.id) == "deleted"
        assert await service.get_variant(variant.id) is None

    async def test_last_variant_cannot_be_deleted(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)
        variant = await make_variant(db_session, product.id)
        with pytest.raises(APIException) as exc_info:
            await ProductService(db_session).delete_variant(variant.id)
        assert exc_info.value.status_code == 400

    async def test_sold_variant_is_archived_not_deleted(self, db_session, test_user):
        from models.commerce.orders import Order, OrderItem
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)
        await make_variant(db_session, product.id)
        variant = await make_variant(db_session, product.id)
        order = Order(id=uuid7(), order_number=f"ORD-{uuid4().hex[:8]}", user_id=test_user.id, subtotal=20, total_amount=20,
                      billing_address={}, shipping_address={})
        db_session.add(order)
        await db_session.flush()
        db_session.add(OrderItem(id=uuid7(), order_id=order.id, variant_id=variant.id, quantity=1, price_per_unit=20, total_price=20))
        await db_session.commit()

        service = ProductService(db_session)
        assert await service.delete_variant(variant.id) == "archived"
        assert (await service.get_variant(variant.id)).is_active is False

    async def test_sale_price_can_be_cleared(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)
        variant = await make_variant(db_session, product.id, base_price=20.0, sale_price=15.0)
        updated = await ProductService(db_session).update_variant(variant.id, VariantUpdate(sale_price=None))
        assert updated.sale_price is None
        assert updated.current_price == 20.0

    async def test_delete_unknown_variant_returns_none(self, db_session):
        assert await ProductService(db_session).delete_variant(uuid4()) is None

    async def test_deleting_the_main_image_promotes_the_next(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)
        variant = await make_variant(db_session, product.id)
        service = ProductService(db_session)
        first = await service.create_image(variant.id, "https://img/1.jpg", is_primary=True, sort_order=0)
        second = await service.create_image(variant.id, "https://img/2.jpg", sort_order=1)
        assert await service.delete_image(UUID(first["id"])) is True
        assert (await service.get_image(UUID(second["id"])))["is_primary"] is True


class TestProductCrud:

    async def test_create_product_with_default_variant(self, db_session):
        cat = await make_category(db_session)
        service = ProductService(db_session)
        result = await service.create(ProductCreate(
            name="New Product", slug=f"new-{uuid4().hex[:8]}", category_id=cat.id, base_price=15.0, sale_price=12.0
        ), created_by=uuid4())
        assert result.name == "New Product"

    async def test_update_product_name(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)

        service = ProductService(db_session)
        result = await service.update(product.id, ProductUpdate(name="Renamed"), user_id=uuid4(), is_admin=True)
        assert result.name == "Renamed"

    async def test_update_requires_admin(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)

        service = ProductService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.update(product.id, ProductUpdate(name="Renamed"), user_id=uuid4(), is_admin=False)
        assert exc_info.value.status_code == 403

    async def test_update_unknown_product_raises_404(self, db_session):
        service = ProductService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.update(uuid4(), ProductUpdate(name="X"), user_id=uuid4(), is_admin=True)
        assert exc_info.value.status_code == 404

    async def test_moderate_approves_product(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id, status=ProductStatus.DRAFT)

        service = ProductService(db_session)
        result = await service.moderate(product.id, "approved")
        assert result.is_active is True

    async def test_moderate_rejects_product(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)

        service = ProductService(db_session)
        result = await service.moderate(product.id, "rejected")
        assert result.is_active is False

    async def test_moderate_unknown_action_raises_400(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)

        service = ProductService(db_session)
        with pytest.raises(Exception):
            await service.moderate(product.id, "not_a_real_action")

    async def test_moderate_stores_notes_in_metadata(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)

        service = ProductService(db_session)
        result = await service.moderate(product.id, "rejected", notes="Missing nutrition label")

        refreshed = await db_session.get(Product, product.id)
        assert refreshed.product_metadata["moderation_notes"] == "Missing nutrition label"

    async def test_set_featured(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id, is_featured=False)

        service = ProductService(db_session)
        result = await service.set_featured(product.id, True)
        assert result.is_featured is True

    async def test_delete_product(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)

        service = ProductService(db_session)
        await service.delete(product.id, user_id=uuid4(), is_admin=True)
        assert await service.get(product_id=product.id) is None

    async def test_delete_requires_admin(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)

        service = ProductService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.delete(product.id, user_id=uuid4(), is_admin=False)
        assert exc_info.value.status_code == 403


class TestImageCrud:

    async def test_create_get_update_delete_image(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)
        variant = await make_variant(db_session, product.id)

        service = ProductService(db_session)
        image = await service.create_image(variant.id, url="https://example.com/a.jpg")
        assert image["url"] == "https://example.com/a.jpg"

        fetched = await service.get_image(image["id"])
        assert fetched["id"] == image["id"]

        images = await service.list_images(variant.id)
        assert len(images) == 1

        updated = await service.update_image(image["id"], alt_text="New alt")
        assert updated["alt_text"] == "New alt"

        assert await service.delete_image(image["id"]) is True
        assert await service.get_image(image["id"]) is None

    async def test_create_image_unknown_variant_raises_404(self, db_session):
        service = ProductService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.create_image(uuid4(), url="https://example.com/a.jpg")
        assert exc_info.value.status_code == 404

    async def test_create_image_as_primary_unsets_previous_primary(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)
        variant = await make_variant(db_session, product.id)
        service = ProductService(db_session)

        first = await service.create_image(variant.id, url="https://example.com/first.jpg", is_primary=True)
        assert first["is_primary"] is True

        second = await service.create_image(variant.id, url="https://example.com/second.jpg", is_primary=True)
        assert second["is_primary"] is True

        refreshed_first = await service.get_image(first["id"])
        assert refreshed_first["is_primary"] is False

    async def test_update_image_to_primary_unsets_previous_primary(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)
        variant = await make_variant(db_session, product.id)
        service = ProductService(db_session)
        first = await service.create_image(variant.id, url="https://example.com/first.jpg", is_primary=True)
        second = await service.create_image(variant.id, url="https://example.com/second.jpg", is_primary=False)

        updated = await service.update_image(second["id"], is_primary=True)
        assert updated["is_primary"] is True

        refreshed_first = await service.get_image(first["id"])
        assert refreshed_first["is_primary"] is False

    async def test_update_image_individual_fields(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)
        variant = await make_variant(db_session, product.id)
        service = ProductService(db_session)
        image = await service.create_image(variant.id, url="https://example.com/original.jpg", sort_order=1)

        updated_url = await service.update_image(image["id"], url="https://example.com/changed.jpg")
        assert updated_url["url"] == "https://example.com/changed.jpg"

        updated_sort = await service.update_image(image["id"], sort_order=9)
        assert updated_sort["sort_order"] == 9


class TestConvertVariantToResponseFallback:
    """_convert_variant_to_response() falls back to a minimal, getattr-built response
    if variant.to_dict()/model_validate() blow up on malformed data - nothing in the
    DB schema stops a JSON/text column from holding something the response schema
    can't parse, so this is real defensive behavior, not paranoia."""

    def test_falls_back_when_to_dict_raises(self):
        variant = ProductVariant(
            id=uuid4(), product_id=uuid4(), sku="SKU-BROKEN", name="Broken",
            base_price=Decimal("10.0"), sale_price=None, is_active=True,
            tags=12345,  # not a string - to_dict() unconditionally calls self.tags.split(",")
        )
        variant.images = []
        variant.inventory = None
        variant.created_at = datetime.utcnow()
        variant.updated_at = None
        service = ProductService(None)

        result = service._convert_variant_to_response(variant)
        assert result.sku == "SKU-BROKEN"
        assert result.base_price == 10.0
        assert result.tags == []  # fallback default - not derived from the broken `tags`


class TestConvertProductToResponseFallback:
    """_convert_product_to_response() has its own per-variant, per-primary-variant,
    and whole-product fallbacks - each keeps one bad record from taking down the
    entire response instead of propagating."""

    async def test_skips_invalid_variant_and_drops_primary_when_it_was_cheapest(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)
        good = await make_variant(db_session, product.id, base_price=50.0)
        broken = await make_variant(db_session, product.id, base_price=10.0)
        # `attributes` is a plain JSON column - nothing stops it from holding a list
        # instead of the dict VariantResponse.attributes requires.
        broken.attributes = ["not", "a", "dict"]
        db_session.add(broken)
        await db_session.commit()

        service = ProductService(db_session)
        result = await service.get(product_id=product.id)

        assert [v.id for v in result.variants] == [good.id]
        # `broken` was the cheapest variant, so it would have been primary_variant;
        # its conversion fails too, and the fallback leaves primary_variant unset
        # rather than raising.
        assert result.primary_variant is None

    async def test_outer_fallback_preserves_is_featured(self, db_session, monkeypatch):
        """Regression test for a real bug: the whole-product fallback used to build
        ProductResponse(featured=...) - but the field is named `is_featured`, so
        pydantic silently dropped it and every fallback response reported
        is_featured=False regardless of the product's actual value."""
        import schemas.catalog.category as category_schema

        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id, is_featured=True)

        def boom(*args, **kwargs):
            raise RuntimeError("boom")
        monkeypatch.setattr(category_schema.CategoryBrief, "model_validate", classmethod(boom))

        service = ProductService(db_session)
        result = await service.get(product_id=product.id)

        assert result.is_featured is True
        assert result.variants == []
        assert result.primary_variant is None


class TestListMoreFilters:

    async def test_filters_by_min_rating(self, db_session):
        cat = await make_category(db_session)
        await make_product(db_session, category_id=cat.id, name="Low Rated", rating_average=2.0)
        await make_product(db_session, category_id=cat.id, name="High Rated", rating_average=4.5)

        service = ProductService(db_session)
        result = await service.list(filters={"min_rating": 4})
        names = [p.name for p in result["data"]]
        assert "High Rated" in names
        assert "Low Rated" not in names

    async def test_filters_by_max_rating(self, db_session):
        cat = await make_category(db_session)
        await make_product(db_session, category_id=cat.id, name="Low Rated", rating_average=2.0)
        await make_product(db_session, category_id=cat.id, name="High Rated", rating_average=4.5)

        service = ProductService(db_session)
        result = await service.list(filters={"max_rating": 3})
        names = [p.name for p in result["data"]]
        assert "Low Rated" in names
        assert "High Rated" not in names


    async def test_filters_by_is_bestseller(self, db_session):
        cat = await make_category(db_session)
        await make_product(db_session, category_id=cat.id, name="Bestseller", is_bestseller=True)
        await make_product(db_session, category_id=cat.id, name="Regular", is_bestseller=False)

        service = ProductService(db_session)
        result = await service.list(filters={"is_bestseller": True})
        names = [p.name for p in result["data"]]
        assert "Bestseller" in names
        assert "Regular" not in names

    async def test_filters_by_availability_false_excludes_in_stock(self, db_session):
        cat = await make_category(db_session)
        in_stock = await make_product(db_session, category_id=cat.id, name="In Stock")
        v1 = await make_variant(db_session, in_stock.id)
        await make_inventory(db_session, v1.id, quantity_available=5)
        out_of_stock = await make_product(db_session, category_id=cat.id, name="Out Of Stock")
        v2 = await make_variant(db_session, out_of_stock.id)
        await make_inventory(db_session, v2.id, quantity_available=0)

        service = ProductService(db_session)
        result = await service.list(filters={"availability": False})
        names = [p.name for p in result["data"]]
        assert "Out Of Stock" in names
        assert "In Stock" not in names


class TestReadCaching:
    """get_variant/list_variants cache their result for a few seconds (product_read_cache) -
    a second call within that window must be served from cache, not recomputed."""

    async def test_get_variant_is_cached_on_second_call(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)
        variant = await make_variant(db_session, product.id)

        service = ProductService(db_session)
        first = await service.get_variant(variant.id)
        second = await service.get_variant(variant.id)
        assert second is first

    async def test_list_variants_is_cached_on_second_call(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)
        await make_variant(db_session, product.id)

        service = ProductService(db_session)
        first = await service.list_variants(product.id)
        second = await service.list_variants(product.id)
        assert second is first


class TestCreateVariantWithImages:

    async def test_creates_images_from_urls(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)

        service = ProductService(db_session)
        variant = await service.create_variant(product.id, VariantCreate(
            name="Large", base_price=29.99, sale_price=24.99, stock=10,
            image_urls=["https://example.com/a.jpg", "https://example.com/b.jpg"],
        ))
        assert len(variant.images) == 2
        assert variant.primary_image.url == "https://example.com/a.jpg"


class TestUpdateVariantEdgeCases:

    async def test_creates_inventory_when_none_existed(self, db_session):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)
        variant = await make_variant(db_session, product.id)  # no inventory made

        service = ProductService(db_session)
        updated = await service.update_variant(variant.id, VariantUpdate(stock=42))
        assert updated.stock == 42


class TestCreateWarehouseLocationAndImages:

    async def test_uses_main_warehouse_when_present(self, db_session):
        location = WarehouseLocation(id=uuid4(), name="Main Warehouse")
        db_session.add(location)
        await db_session.commit()

        cat = await make_category(db_session)
        service = ProductService(db_session)
        result = await service.create(ProductCreate(
            name="Located Product", slug=f"located-{uuid4().hex[:8]}", category_id=cat.id,
            base_price=10.0, sale_price=8.0, quantity=5,
        ), created_by=uuid4())

        variant = result.variants[0]
        inventory = (await db_session.execute(
            select(Inventory).where(Inventory.variant_id == variant.id)
        )).scalar_one()
        assert inventory.location_id == location.id

    async def test_falls_back_to_default_named_warehouse(self, db_session):
        location = WarehouseLocation(id=uuid4(), name="Default")
        db_session.add(location)
        await db_session.commit()

        cat = await make_category(db_session)
        service = ProductService(db_session)
        result = await service.create(ProductCreate(
            name="Fallback Located", slug=f"fallback-{uuid4().hex[:8]}", category_id=cat.id,
            base_price=10.0, sale_price=8.0, quantity=5,
        ), created_by=uuid4())

        variant = result.variants[0]
        inventory = (await db_session.execute(
            select(Inventory).where(Inventory.variant_id == variant.id)
        )).scalar_one()
        assert inventory.location_id == location.id

    async def test_no_warehouse_location_leaves_it_unset(self, db_session):
        cat = await make_category(db_session)
        service = ProductService(db_session)
        result = await service.create(ProductCreate(
            name="No Warehouse", slug=f"nowarehouse-{uuid4().hex[:8]}", category_id=cat.id,
            base_price=10.0, sale_price=8.0, quantity=5,
        ), created_by=uuid4())

        variant = result.variants[0]
        inventory = (await db_session.execute(
            select(Inventory).where(Inventory.variant_id == variant.id)
        )).scalar_one()
        assert inventory.location_id is None

    async def test_explicit_variants_with_image_urls(self, db_session):
        cat = await make_category(db_session)
        service = ProductService(db_session)
        result = await service.create(ProductCreate(
            name="Gallery Product", slug=f"gallery-{uuid4().hex[:8]}", category_id=cat.id,
            sale_price=8.0,
            variants=[VariantCreate(
                name="V1", base_price=10.0, sale_price=8.0, stock=5,
                image_urls=["https://example.com/1.jpg", "https://example.com/2.jpg"],
            )],
        ), created_by=uuid4())

        variant = result.variants[0]
        assert len(variant.images) == 2


class TestDeleteProductAssociatedData:

    async def test_blocked_when_variant_has_order_history(self, db_session, test_user):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)
        variant = await make_variant(db_session, product.id)

        order = Order(
            id=uuid7(), order_number=f"ORD-{uuid4().hex[:10].upper()}", user_id=test_user.id,
            order_status=OrderStatus.DELIVERED, payment_status=PaymentStatus.PAID,
            fulfillment_status=FulfillmentStatus.FULFILLED,
            subtotal=Decimal("10.0"), shipping_cost=Decimal("0.0"), tax_amount=Decimal("0.0"), total_amount=Decimal("10.0"),
            billing_address={"street": "1 Test St"}, shipping_address={"street": "1 Test St"},
        )
        db_session.add(order)
        await db_session.flush()
        db_session.add(OrderItem(
            id=uuid7(), order_id=order.id, variant_id=variant.id, quantity=1,
            price_per_unit=Decimal("10.0"), total_price=Decimal("10.0"),
        ))
        await db_session.commit()

        service = ProductService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.delete(product.id, user_id=uuid4(), is_admin=True)
        assert exc_info.value.status_code == 400

    async def test_deletes_reviews_and_cart_items(self, db_session, test_user):
        cat = await make_category(db_session)
        product = await make_product(db_session, category_id=cat.id)
        variant = await make_variant(db_session, product.id)

        db_session.add(Review(id=uuid7(), user_id=test_user.id, product_id=product.id, rating=5))
        cart = Cart(id=uuid4(), user_id=test_user.id)
        db_session.add(cart)
        await db_session.flush()
        db_session.add(CartItem(
            id=uuid4(), cart_id=cart.id, product_id=product.id, variant_id=variant.id,
            quantity=1, price_per_unit=Decimal("10.0"),
        ))
        await db_session.commit()

        service = ProductService(db_session)
        await service.delete(product.id, user_id=uuid4(), is_admin=True)

        assert await service.get(product_id=product.id) is None
        remaining_reviews = (await db_session.execute(select(Review).where(Review.product_id == product.id))).scalars().all()
        assert remaining_reviews == []
        remaining_cart_items = (await db_session.execute(select(CartItem).where(CartItem.product_id == product.id))).scalars().all()
        assert remaining_cart_items == []


@pytest.mark.parametrize("base, sale, expected", [
    (10.0, None, None), (10.0, 0, None), (10.0, 10.0, None), (10.0, 12.0, None), (10.0, 7.5, 7.5),
])
def test_only_a_price_below_base_counts_as_a_sale(base, sale, expected):
    from services.catalog.products import sale_price_or_none
    assert sale_price_or_none(base, sale) == expected
