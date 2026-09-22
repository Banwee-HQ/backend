"""Tests for api/catalog/products.py - /v1/products endpoints."""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.fixture
async def created_category(async_client: AsyncClient, admin_headers):
    response = await async_client.post("/v1/categories/",
        headers=admin_headers,
        json={"name": "Grains & Pulses", "slug": f"grains-pulses-{uuid4().hex[:8]}"}
    )
    return response.json()["data"]


@pytest.fixture
async def created_product(async_client: AsyncClient, admin_headers, sample_product_data, created_category):
    sample_product_data["category_id"] = created_category["id"]
    response = await async_client.post("/v1/products/", headers=admin_headers, json=sample_product_data)
    return response.json()["data"]


@pytest.mark.api
class TestProductEndpoints:

    async def test_home(self, async_client: AsyncClient):
        """GET /v1/products/home - Get home data."""
        response = await async_client.get("/v1/products/home/")
        assert response.status_code == 200
        data = response.json()
        assert "categories" in data["data"]
        assert "featured" in data["data"]

    async def test_list(self, async_client: AsyncClient):
        """GET /v1/products/ - List products."""
        response = await async_client.get("/v1/products/?limit=10")
        assert response.status_code == 200
        assert response.json()["success"] is True

    async def test_list_with_filters(self, async_client: AsyncClient):
        """GET /v1/products/ - List with price filters."""
        response = await async_client.get("/v1/products/?min_price=10&max_price=100")
        assert response.status_code == 200

    async def test_list_with_sorting(self, async_client: AsyncClient):
        """GET /v1/products/ - List with sorting."""
        response = await async_client.get("/v1/products/?sort_by=price&sort_order=asc")
        assert response.status_code == 200

    async def test_list_with_search(self, async_client: AsyncClient):
        """GET /v1/products/ - Search products."""
        response = await async_client.get("/v1/products/?q=organic")
        assert response.status_code == 200

    async def test_featured(self, async_client: AsyncClient):
        """GET /v1/products/featured - List featured products."""
        response = await async_client.get("/v1/products/featured/")
        assert response.status_code == 200

    async def test_deals(self, async_client: AsyncClient):
        """GET /v1/products/deals - List products on sale."""
        response = await async_client.get("/v1/products/deals/")
        assert response.status_code == 200

    async def test_get_by_id_not_found(self, async_client: AsyncClient):
        """GET /v1/products/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/products/{uuid4()}/")
        assert response.status_code == 404

    async def test_get_by_id(self, async_client: AsyncClient, created_product):
        """GET /v1/products/{id} - Get an existing product."""
        response = await async_client.get(f"/v1/products/{created_product['id']}/")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == created_product["id"]

    async def test_get_by_slug(self, async_client: AsyncClient, created_product):
        """GET /v1/products/{slug} - Get a product by slug."""
        response = await async_client.get(f"/v1/products/{created_product['slug']}/")
        assert response.status_code == 200

    async def test_recommendations(self, async_client: AsyncClient, created_product):
        """GET /v1/products/{id}/recommendations - Get recommendations for a real product."""
        response = await async_client.get(f"/v1/products/{created_product['id']}/recommendations/")
        assert response.status_code == 200

    async def test_variants(self, async_client: AsyncClient, created_product):
        """GET /v1/products/{id}/variants - A newly created product has a default variant."""
        response = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        assert response.status_code == 200
        assert len(response.json()["data"]) >= 1

    async def test_get_variant(self, async_client: AsyncClient, created_product):
        """GET /v1/products/variants/{id} - Get the default variant created with the product."""
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]

        response = await async_client.get(f"/v1/products/variants/{variant_id}/")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == variant_id

    async def test_create_as_admin(self, async_client: AsyncClient, admin_headers, sample_product_data, created_category):
        """POST /v1/products/ - Create product (admin)."""
        sample_product_data["category_id"] = created_category["id"]
        response = await async_client.post("/v1/products/", headers=admin_headers, json=sample_product_data)
        assert response.status_code == 200
        assert response.json()["data"]["name"] == sample_product_data["name"]

    async def test_create_requires_admin(self, async_client: AsyncClient, auth_headers, sample_product_data, created_category):
        """POST /v1/products/ - Non-admin is forbidden."""
        sample_product_data["category_id"] = created_category["id"]
        response = await async_client.post("/v1/products/", headers=auth_headers, json=sample_product_data)
        assert response.status_code == 403

    async def test_update_as_admin(self, async_client: AsyncClient, admin_headers, created_product):
        """PATCH /v1/products/{id} - Update product (admin)."""
        response = await async_client.patch(f"/v1/products/{created_product['id']}/",
            headers=admin_headers, json={"name": "Updated Product"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Updated Product"

    async def test_update_not_found(self, async_client: AsyncClient, admin_headers):
        """PATCH /v1/products/{id} - Unknown ID returns 404."""
        response = await async_client.patch(f"/v1/products/{uuid4()}/",
            headers=admin_headers, json={"name": "Updated"}
        )
        assert response.status_code == 404

    async def test_delete_as_admin(self, async_client: AsyncClient, admin_headers, created_product):
        """DELETE /v1/products/{id} - Delete product (admin)."""
        response = await async_client.delete(f"/v1/products/{created_product['id']}/", headers=admin_headers)
        assert response.status_code == 200

        get_resp = await async_client.get(f"/v1/products/{created_product['id']}/")
        assert get_resp.status_code == 404

    async def test_update_requires_admin(self, async_client: AsyncClient, auth_headers, created_product):
        response = await async_client.patch(f"/v1/products/{created_product['id']}/",
            headers=auth_headers, json={"name": "Hacked"}
        )
        assert response.status_code == 403

    async def test_delete_requires_admin(self, async_client: AsyncClient, auth_headers, created_product):
        response = await async_client.delete(f"/v1/products/{created_product['id']}/", headers=auth_headers)
        assert response.status_code == 403

    async def test_delete_not_found(self, async_client: AsyncClient, admin_headers):
        response = await async_client.delete(f"/v1/products/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_recommendations_unknown_product(self, async_client: AsyncClient):
        response = await async_client.get(f"/v1/products/{uuid4()}/recommendations/")
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_variants_unknown_product(self, async_client: AsyncClient):
        response = await async_client.get(f"/v1/products/{uuid4()}/variants/")
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_get_variant_not_found(self, async_client: AsyncClient):
        response = await async_client.get(f"/v1/products/variants/{uuid4()}/")
        assert response.status_code == 404

    async def test_create_variant(self, async_client: AsyncClient, admin_headers, created_product):
        """POST /v1/products/{id}/variants - Create variant (admin)."""
        variant_data = {"name": "Large", "base_price": 99.99, "sale_price": 89.99, "stock": 100}
        response = await async_client.post(f"/v1/products/{created_product['id']}/variants/",
            headers=admin_headers, json=variant_data
        )
        assert response.status_code == 201
        assert response.json()["data"]["name"] == "Large"

    async def test_update_variant(self, async_client: AsyncClient, admin_headers, created_product):
        """PATCH /v1/products/variants/{id} - Update variant (admin)."""
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]

        response = await async_client.patch(f"/v1/products/variants/{variant_id}/",
            headers=admin_headers, json={"sale_price": 15.00}
        )
        assert response.status_code == 200
        assert response.json()["data"]["sale_price"] == 15.00

    async def test_delete_variant(self, async_client: AsyncClient, admin_headers, created_product):
        """DELETE /v1/products/variants/{id} - Delete variant (admin)."""
        create_resp = await async_client.post(f"/v1/products/{created_product['id']}/variants/",
            headers=admin_headers, json={"name": "Extra", "base_price": 10.0, "sale_price": 8.0}
        )
        variant_id = create_resp.json()["data"]["id"]

        response = await async_client.delete(f"/v1/products/variants/{variant_id}/", headers=admin_headers)
        assert response.status_code == 200

    async def test_delete_variant_not_found(self, async_client: AsyncClient, admin_headers):
        response = await async_client.delete(f"/v1/products/variants/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_create_variant_requires_admin(self, async_client: AsyncClient, auth_headers, created_product):
        response = await async_client.post(f"/v1/products/{created_product['id']}/variants/",
            headers=auth_headers, json={"name": "Large", "base_price": 99.99}
        )
        assert response.status_code == 403

    async def test_update_variant_requires_admin(self, async_client: AsyncClient, auth_headers, created_product):
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]
        response = await async_client.patch(f"/v1/products/variants/{variant_id}/",
            headers=auth_headers, json={"sale_price": 1.0}
        )
        assert response.status_code == 403

    async def test_create_image(self, async_client: AsyncClient, admin_headers, created_product):
        """POST /v1/products/variants/{id}/images - Create image (admin)."""
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]

        response = await async_client.post(f"/v1/products/variants/{variant_id}/images/",
            headers=admin_headers, json={"url": "https://example.com/img.jpg", "alt_text": "Product image"}
        )
        assert response.status_code == 201

    async def test_list_images(self, async_client: AsyncClient, admin_headers, created_product):
        """GET /v1/products/variants/{id}/images - List images for a variant."""
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]
        await async_client.post(f"/v1/products/variants/{variant_id}/images/",
            headers=admin_headers, json={"url": "https://example.com/img.jpg"}
        )

        response = await async_client.get(f"/v1/products/variants/{variant_id}/images/")
        assert response.status_code == 200
        assert len(response.json()["data"]) >= 1

    async def test_get_image(self, async_client: AsyncClient, admin_headers, created_product):
        """GET /v1/products/images/{id} - Get a specific image."""
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]
        created = await async_client.post(f"/v1/products/variants/{variant_id}/images/",
            headers=admin_headers, json={"url": "https://example.com/img.jpg"}
        )
        image_id = created.json()["data"]["id"]

        response = await async_client.get(f"/v1/products/images/{image_id}/")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == image_id

    async def test_get_image_not_found(self, async_client: AsyncClient):
        """GET /v1/products/images/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/products/images/{uuid4()}/")
        assert response.status_code == 404

    async def test_update_image(self, async_client: AsyncClient, admin_headers, created_product):
        """PATCH /v1/products/images/{id} - Update image (admin)."""
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]
        created = await async_client.post(f"/v1/products/variants/{variant_id}/images/",
            headers=admin_headers, json={"url": "https://example.com/img.jpg"}
        )
        image_id = created.json()["data"]["id"]

        response = await async_client.patch(f"/v1/products/images/{image_id}/",
            headers=admin_headers, json={"alt_text": "Updated alt text"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["alt_text"] == "Updated alt text"

    async def test_delete_image(self, async_client: AsyncClient, admin_headers, created_product):
        """DELETE /v1/products/images/{id} - Delete image (admin)."""
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]
        created = await async_client.post(f"/v1/products/variants/{variant_id}/images/",
            headers=admin_headers, json={"url": "https://example.com/img.jpg"}
        )
        image_id = created.json()["data"]["id"]

        response = await async_client.delete(f"/v1/products/images/{image_id}/", headers=admin_headers)
        assert response.status_code == 200

        get_after = await async_client.get(f"/v1/products/images/{image_id}/")
        assert get_after.status_code == 404

    async def test_moderate(self, async_client: AsyncClient, admin_headers, created_product):
        """PATCH /v1/products/{id}/moderate - Moderate product (admin)."""
        response = await async_client.patch(f"/v1/products/{created_product['id']}/moderate/",
            headers=admin_headers, json={"status": "approved"}
        )
        assert response.status_code == 200

    async def test_moderate_requires_admin(self, async_client: AsyncClient, auth_headers, created_product):
        response = await async_client.patch(f"/v1/products/{created_product['id']}/moderate/",
            headers=auth_headers, json={"status": "approved"}
        )
        assert response.status_code == 403

    async def test_feature(self, async_client: AsyncClient, admin_headers, created_product):
        """PATCH /v1/products/{id}/feature - Feature product (admin)."""
        response = await async_client.patch(f"/v1/products/{created_product['id']}/feature/",
            headers=admin_headers, params={"featured": True}
        )
        assert response.status_code == 200
        assert response.json()["data"]["is_featured"] is True

    async def test_feature_requires_admin(self, async_client: AsyncClient, auth_headers, created_product):
        response = await async_client.patch(f"/v1/products/{created_product['id']}/feature/",
            headers=auth_headers, params={"featured": True}
        )
        assert response.status_code == 403

    async def test_create_image_requires_admin(self, async_client: AsyncClient, auth_headers, created_product):
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]
        response = await async_client.post(f"/v1/products/variants/{variant_id}/images/",
            headers=auth_headers, json={"url": "https://example.com/img.jpg"}
        )
        assert response.status_code == 403

    async def test_update_image_not_found(self, async_client: AsyncClient, admin_headers):
        response = await async_client.patch(f"/v1/products/images/{uuid4()}/",
            headers=admin_headers, json={"alt_text": "Nowhere"}
        )
        assert response.status_code == 404

    async def test_delete_image_not_found(self, async_client: AsyncClient, admin_headers):
        response = await async_client.delete(f"/v1/products/images/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404


@pytest.mark.api
class TestVariantSyncViaProductUpdate:
    """PATCH /v1/products/{id} with a `variants` array - bulk update/create/delete of
    variants (plus nested image sync and stock/inventory) in one request."""

    async def test_update_existing_variant_fields_and_stock(self, async_client: AsyncClient, admin_headers, created_product):
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant = variants_resp.json()["data"][0]

        response = await async_client.patch(f"/v1/products/{created_product['id']}/",
            headers=admin_headers, json={
                "variants": [{"id": variant["id"], "name": "Renamed Variant", "stock": 77}]
            }
        )
        assert response.status_code == 200

        updated = await async_client.get(f"/v1/products/variants/{variant['id']}/")
        assert updated.json()["data"]["name"] == "Renamed Variant"
        assert updated.json()["data"]["stock"] == 77

    async def test_create_new_variant_via_array(self, async_client: AsyncClient, admin_headers, created_product):
        response = await async_client.patch(f"/v1/products/{created_product['id']}/",
            headers=admin_headers, json={
                "variants": [{"name": "Brand New Variant", "base_price": 12.5, "stock": 8}]
            }
        )
        assert response.status_code == 200

        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        names = [v["name"] for v in variants_resp.json()["data"]]
        assert "Brand New Variant" in names

    async def test_add_and_remove_image_via_variant_sync(self, async_client: AsyncClient, admin_headers, created_product):
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]

        added = await async_client.patch(f"/v1/products/{created_product['id']}/",
            headers=admin_headers, json={
                "variants": [{"id": variant_id, "images": [{"url": "https://example.com/a.jpg"}]}]
            }
        )
        assert added.status_code == 200
        images_resp = await async_client.get(f"/v1/products/variants/{variant_id}/images/")
        assert len(images_resp.json()["data"]) == 1

        removed = await async_client.patch(f"/v1/products/{created_product['id']}/",
            headers=admin_headers, json={
                "variants": [{"id": variant_id, "images": []}]
            }
        )
        assert removed.status_code == 200
        images_after = await async_client.get(f"/v1/products/variants/{variant_id}/images/")
        assert images_after.json()["data"] == []

    async def test_delete_variant_removed_from_array(self, async_client: AsyncClient, admin_headers, created_product):
        """The variants array is a full replacement set: any existing variant id not
        included gets deleted. Keep the original by id, add a second to delete later."""
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        keeper = variants_resp.json()["data"][0]

        await async_client.patch(f"/v1/products/{created_product['id']}/",
            headers=admin_headers, json={
                "variants": [{"id": keeper["id"]}, {"name": "Extra", "base_price": 5.0}]
            }
        )
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        all_variants = variants_resp.json()["data"]
        assert len(all_variants) == 2
        to_delete = next(v for v in all_variants if v["id"] != keeper["id"])

        response = await async_client.patch(f"/v1/products/{created_product['id']}/",
            headers=admin_headers, json={"variants": [{"id": keeper["id"]}]}
        )
        assert response.status_code == 200

        after = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        ids = [v["id"] for v in after.json()["data"]]
        assert keeper["id"] in ids
        assert to_delete["id"] not in ids

    async def test_delete_variant_referenced_by_order_is_blocked(self, async_client: AsyncClient, admin_headers,
                                                                    created_product, db_session, test_user):
        """A variant with order history can't be dropped via the sync - it would orphan the order item."""
        from models.commerce.orders import Order, OrderItem, OrderStatus, PaymentStatus, FulfillmentStatus
        from core.utils.uuid_utils import uuid7
        from decimal import Decimal

        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]

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
            id=uuid7(), order_id=order.id, variant_id=variant_id, quantity=1,
            price_per_unit=Decimal("10.0"), total_price=Decimal("10.0"),
        ))
        await db_session.commit()

        # Keep the referenced variant by id while adding a second one.
        await async_client.patch(f"/v1/products/{created_product['id']}/",
            headers=admin_headers, json={
                "variants": [{"id": variant_id}, {"name": "Other", "base_price": 5.0}]
            }
        )
        after_add = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        other = next(v for v in after_add.json()["data"] if v["id"] != variant_id)

        # Now omit the referenced variant - the sync would try to delete it.
        response = await async_client.patch(f"/v1/products/{created_product['id']}/",
            headers=admin_headers, json={"variants": [{"id": other["id"]}]}
        )
        assert response.status_code == 400
