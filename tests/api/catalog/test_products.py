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

    async def test_feature(self, async_client: AsyncClient, admin_headers, created_product):
        """PATCH /v1/products/{id}/feature - Feature product (admin)."""
        response = await async_client.patch(f"/v1/products/{created_product['id']}/feature/",
            headers=admin_headers, params={"featured": True}
        )
        assert response.status_code == 200
        assert response.json()["data"]["is_featured"] is True
