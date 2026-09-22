"""Tests for api/catalog/category.py - /v1/categories endpoints."""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.fixture
async def created_category(async_client: AsyncClient, admin_headers):
    response = await async_client.post("/v1/categories/",
        headers=admin_headers,
        json={"name": "Beverages", "slug": f"beverages-{uuid4().hex[:8]}"}
    )
    return response.json()["data"]


@pytest.mark.api
class TestCategoryEndpoints:

    async def test_list(self, async_client: AsyncClient, created_category):
        """GET /v1/categories/ - List categories."""
        response = await async_client.get("/v1/categories/")
        assert response.status_code == 200
        assert response.json()["success"] is True

    async def test_tree(self, async_client: AsyncClient, created_category):
        """GET /v1/categories/tree/ - Nested category tree."""
        response = await async_client.get("/v1/categories/tree/")
        assert response.status_code == 200

    async def test_get_by_id(self, async_client: AsyncClient, created_category):
        """GET /v1/categories/{id} - Get a category."""
        response = await async_client.get(f"/v1/categories/{created_category['id']}/")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == created_category["id"]

    async def test_get_by_id_not_found(self, async_client: AsyncClient):
        """GET /v1/categories/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/categories/{uuid4()}/")
        assert response.status_code == 404

    async def test_create_as_admin(self, async_client: AsyncClient, admin_headers):
        """POST /v1/categories/ - Create category (admin)."""
        response = await async_client.post("/v1/categories/",
            headers=admin_headers, json={"name": "Snacks", "slug": f"snacks-{uuid4().hex[:8]}"}
        )
        assert response.status_code == 201

    async def test_create_requires_admin(self, async_client: AsyncClient, auth_headers):
        """POST /v1/categories/ - Non-admin is forbidden."""
        response = await async_client.post("/v1/categories/",
            headers=auth_headers, json={"name": "Snacks", "slug": f"snacks-{uuid4().hex[:8]}"}
        )
        assert response.status_code == 403

    async def test_create_duplicate_slug(self, async_client: AsyncClient, admin_headers, created_category):
        """POST /v1/categories/ - Duplicate slug is rejected."""
        response = await async_client.post("/v1/categories/",
            headers=admin_headers, json={"name": "Another", "slug": created_category["slug"]}
        )
        assert response.status_code == 400

    async def test_update_as_admin(self, async_client: AsyncClient, admin_headers, created_category):
        """PATCH /v1/categories/{id} - Update category (admin)."""
        response = await async_client.patch(f"/v1/categories/{created_category['id']}/",
            headers=admin_headers, json={"name": "Updated Name"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Updated Name"

    async def test_delete_as_admin(self, async_client: AsyncClient, admin_headers, created_category):
        """DELETE /v1/categories/{id} - Delete category (admin), no products/children attached."""
        response = await async_client.delete(f"/v1/categories/{created_category['id']}/", headers=admin_headers)
        assert response.status_code == 200

        get_resp = await async_client.get(f"/v1/categories/{created_category['id']}/")
        assert get_resp.status_code == 404

    async def test_delete_with_products_blocked(self, async_client: AsyncClient, admin_headers,
                                                  created_category, sample_product_data):
        """DELETE /v1/categories/{id} - Blocked while a product still references it."""
        sample_product_data["category_id"] = created_category["id"]
        await async_client.post("/v1/products/", headers=admin_headers, json=sample_product_data)

        response = await async_client.delete(f"/v1/categories/{created_category['id']}/", headers=admin_headers)
        assert response.status_code == 400

    async def test_update_not_found(self, async_client: AsyncClient, admin_headers):
        response = await async_client.patch(f"/v1/categories/{uuid4()}/",
            headers=admin_headers, json={"name": "Nowhere"}
        )
        assert response.status_code == 404

    async def test_update_requires_admin(self, async_client: AsyncClient, auth_headers, created_category):
        response = await async_client.patch(f"/v1/categories/{created_category['id']}/",
            headers=auth_headers, json={"name": "Hacked"}
        )
        assert response.status_code == 403

    async def test_delete_not_found(self, async_client: AsyncClient, admin_headers):
        response = await async_client.delete(f"/v1/categories/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_delete_requires_admin(self, async_client: AsyncClient, auth_headers, created_category):
        response = await async_client.delete(f"/v1/categories/{created_category['id']}/", headers=auth_headers)
        assert response.status_code == 403

    async def test_list_active_only(self, async_client: AsyncClient, admin_headers, created_category):
        await async_client.patch(f"/v1/categories/{created_category['id']}/",
            headers=admin_headers, json={"is_active": False}
        )
        response = await async_client.get("/v1/categories/?active_only=true")
        assert response.status_code == 200
        ids = [c["id"] for c in response.json()["data"]]
        assert created_category["id"] not in ids
