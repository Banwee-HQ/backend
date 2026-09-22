"""Tests for services/catalog/products.py - ProductService."""

import pytest
from uuid import uuid4
from decimal import Decimal

from fastapi import HTTPException

from services.catalog.products import ProductService
from schemas.catalog.product import Create as ProductCreate, Update as ProductUpdate, VariantUpdate
from models.catalog.category import Category
from models.catalog.product import Product, ProductVariant, ProductStatus
from models.catalog.inventories import Inventory


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

    async def test_popular_returns_products(self, db_session):
        cat = await make_category(db_session)
        await make_product(db_session, category_id=cat.id, name="Popular")

        service = ProductService(db_session)
        result = await service.popular(limit=10)
        assert isinstance(result, list)


class TestByCategory:

    async def test_returns_products_in_category(self, db_session):
        cat = await make_category(db_session, slug="my-cat")
        await make_product(db_session, category_id=cat.id, name="In Category")

        service = ProductService(db_session)
        result = await service.by_category("my-cat")
        assert result is not None

    async def test_unknown_slug_returns_empty_list(self, db_session):
        service = ProductService(db_session)
        result = await service.by_category("does-not-exist")
        assert result.products == []


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
        variant = await make_variant(db_session, product.id)

        service = ProductService(db_session)
        assert await service.delete_variant(variant.id) is True
        assert await service.get_variant(variant.id) is None

    async def test_delete_unknown_variant_returns_false(self, db_session):
        service = ProductService(db_session)
        assert await service.delete_variant(uuid4()) is False


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
