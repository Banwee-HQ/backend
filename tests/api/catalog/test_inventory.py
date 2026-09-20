"""Tests for api/catalog/inventory.py - /v1/inventory endpoints."""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.fixture
async def created_location(async_client: AsyncClient, admin_headers):
    response = await async_client.post("/v1/inventory/locations/",
        headers=admin_headers, json={"name": f"Warehouse {uuid4().hex[:6]}", "address": "123 Main St"}
    )
    return response.json()["data"]


@pytest.fixture
async def created_variant(async_client: AsyncClient, admin_headers, sample_product_data):
    cat = await async_client.post("/v1/categories/",
        headers=admin_headers, json={"name": "Cat", "slug": f"cat-{uuid4().hex[:8]}"}
    )
    sample_product_data["category_id"] = cat.json()["data"]["id"]
    product = await async_client.post("/v1/products/", headers=admin_headers, json=sample_product_data)
    variants = await async_client.get(f"/v1/products/{product.json()['data']['id']}/variants/")
    return variants.json()["data"][0]


@pytest.mark.api
@pytest.mark.inventory
class TestLocationEndpoints:

    async def test_list(self, async_client: AsyncClient, created_location):
        """GET /v1/inventory/locations/ - List locations."""
        response = await async_client.get("/v1/inventory/locations/")
        assert response.status_code == 200

    async def test_create_as_admin(self, async_client: AsyncClient, admin_headers):
        """POST /v1/inventory/locations/ - Create location (admin)."""
        response = await async_client.post("/v1/inventory/locations/",
            headers=admin_headers, json={"name": "New Warehouse", "address": "1 Depot Rd"}
        )
        assert response.status_code == 201

    async def test_create_requires_admin(self, async_client: AsyncClient, auth_headers):
        """POST /v1/inventory/locations/ - Non-admin is forbidden."""
        response = await async_client.post("/v1/inventory/locations/",
            headers=auth_headers, json={"name": "New Warehouse"}
        )
        assert response.status_code == 403

    async def test_get_by_id(self, async_client: AsyncClient, created_location):
        """GET /v1/inventory/locations/{id} - Get location."""
        response = await async_client.get(f"/v1/inventory/locations/{created_location['id']}/")
        assert response.status_code == 200

    async def test_get_by_id_not_found(self, async_client: AsyncClient):
        """GET /v1/inventory/locations/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/inventory/locations/{uuid4()}/")
        assert response.status_code == 404

    async def test_update_as_admin(self, async_client: AsyncClient, admin_headers, created_location):
        """PATCH /v1/inventory/locations/{id} - Update location (admin)."""
        response = await async_client.patch(f"/v1/inventory/locations/{created_location['id']}/",
            headers=admin_headers, json={"name": "Updated Warehouse"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Updated Warehouse"

    async def test_update_requires_admin(self, async_client: AsyncClient, auth_headers, created_location):
        """PATCH /v1/inventory/locations/{id} - Non-admin is forbidden."""
        response = await async_client.patch(f"/v1/inventory/locations/{created_location['id']}/",
            headers=auth_headers, json={"name": "Hacked"}
        )
        assert response.status_code == 403

    async def test_delete_as_admin(self, async_client: AsyncClient, admin_headers, created_location):
        """DELETE /v1/inventory/locations/{id} - Delete an empty location (admin)."""
        response = await async_client.delete(f"/v1/inventory/locations/{created_location['id']}/", headers=admin_headers)
        assert response.status_code == 200

    async def test_delete_requires_admin(self, async_client: AsyncClient, auth_headers, created_location):
        """DELETE /v1/inventory/locations/{id} - Non-admin is forbidden."""
        response = await async_client.delete(f"/v1/inventory/locations/{created_location['id']}/", headers=auth_headers)
        assert response.status_code == 403


@pytest.mark.api
@pytest.mark.inventory
class TestInventoryItemEndpoints:

    async def test_get_by_variant(self, async_client: AsyncClient, admin_headers, created_variant):
        """GET /v1/inventory/{id} - A variant gets an inventory row automatically on creation."""
        response = await async_client.get(f"/v1/inventory/?product_id={created_variant['product_id']}", headers=admin_headers)
        assert response.status_code == 200

    async def test_create_requires_admin(self, async_client: AsyncClient, auth_headers, created_variant, created_location):
        """POST /v1/inventory/ - Non-admin is forbidden."""
        response = await async_client.post("/v1/inventory/", headers=auth_headers, json={
            "variant_id": created_variant["id"], "location_id": created_location["id"], "quantity": 50
        })
        assert response.status_code == 403

    async def test_create_duplicate_rejected(self, async_client: AsyncClient, admin_headers, created_variant, created_location):
        """POST /v1/inventory/ - A variant already has inventory from creation, so this is rejected."""
        response = await async_client.post("/v1/inventory/", headers=admin_headers, json={
            "variant_id": created_variant["id"], "location_id": created_location["id"], "quantity": 50
        })
        assert response.status_code == 400

    async def test_list(self, async_client: AsyncClient, admin_headers, created_variant):
        """GET /v1/inventory/ - List inventory items."""
        response = await async_client.get("/v1/inventory/", headers=admin_headers)
        assert response.status_code == 200

    async def test_low_stock(self, async_client: AsyncClient, admin_headers, created_variant):
        """GET /v1/inventory/?low_stock=true - Filter by low stock."""
        response = await async_client.get("/v1/inventory/?low_stock=true", headers=admin_headers)
        assert response.status_code == 200


@pytest.mark.api
@pytest.mark.inventory
class TestAdjustmentEndpoints:

    async def test_create_as_admin(self, async_client: AsyncClient, admin_headers, created_variant):
        """POST /v1/inventory/adjustments/ - Create a stock adjustment (admin)."""
        response = await async_client.post("/v1/inventory/adjustments/", headers=admin_headers, json={
            "variant_id": created_variant["id"], "quantity_change": 10, "reason": "Restock"
        })
        assert response.status_code == 200
        assert response.json()["data"]["quantity_available"] == created_variant["stock"] + 10

    async def test_create_requires_admin(self, async_client: AsyncClient, auth_headers, created_variant):
        """POST /v1/inventory/adjustments/ - Non-admin is forbidden."""
        response = await async_client.post("/v1/inventory/adjustments/", headers=auth_headers, json={
            "variant_id": created_variant["id"], "quantity_change": 10, "reason": "Restock"
        })
        assert response.status_code == 403

    async def test_list_requires_admin(self, async_client: AsyncClient, auth_headers):
        """GET /v1/inventory/adjustments/ - Non-admin is forbidden."""
        response = await async_client.get("/v1/inventory/adjustments/", headers=auth_headers)
        assert response.status_code == 403

    async def test_list_as_admin(self, async_client: AsyncClient, admin_headers):
        """GET /v1/inventory/adjustments/ - Admin can list adjustments."""
        response = await async_client.get("/v1/inventory/adjustments/", headers=admin_headers)
        assert response.status_code == 200


@pytest.mark.api
@pytest.mark.inventory
class TestSyncEndpoints:

    async def test_sync_all(self, async_client: AsyncClient, admin_headers, created_variant):
        """POST /v1/inventory/sync-all/ - Admin can resync all product availability."""
        response = await async_client.post("/v1/inventory/sync-all/", headers=admin_headers)
        assert response.status_code == 200

    async def test_sync_product(self, async_client: AsyncClient, admin_headers, created_variant):
        """POST /v1/inventory/sync/product/{id}/ - Resync a single product."""
        response = await async_client.post(
            f"/v1/inventory/sync/product/{created_variant['product_id']}/", headers=admin_headers
        )
        assert response.status_code == 200

    async def test_sync_product_invalid_id(self, async_client: AsyncClient, admin_headers):
        """POST /v1/inventory/sync/product/{id}/ - Malformed ID returns 400."""
        response = await async_client.post("/v1/inventory/sync/product/not-a-uuid/", headers=admin_headers)
        assert response.status_code == 400
