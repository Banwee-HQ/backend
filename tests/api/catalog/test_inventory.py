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

    async def test_list(self, async_client: AsyncClient, admin_headers, created_location):
        """GET /v1/inventory/locations/ - List locations (admin only)."""
        response = await async_client.get("/v1/inventory/locations/", headers=admin_headers)
        assert response.status_code == 200

    async def test_list_requires_admin(self, async_client: AsyncClient, auth_headers):
        """GET /v1/inventory/locations/ - Non-admin is forbidden."""
        response = await async_client.get("/v1/inventory/locations/", headers=auth_headers)
        assert response.status_code == 403

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

    async def test_get_by_id(self, async_client: AsyncClient, admin_headers, created_location):
        """GET /v1/inventory/locations/{id} - Get location (admin only)."""
        response = await async_client.get(f"/v1/inventory/locations/{created_location['id']}/", headers=admin_headers)
        assert response.status_code == 200

    async def test_get_by_id_requires_admin(self, async_client: AsyncClient, auth_headers, created_location):
        """GET /v1/inventory/locations/{id} - Non-admin is forbidden."""
        response = await async_client.get(f"/v1/inventory/locations/{created_location['id']}/", headers=auth_headers)
        assert response.status_code == 403

    async def test_get_by_id_not_found(self, async_client: AsyncClient, admin_headers):
        """GET /v1/inventory/locations/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/inventory/locations/{uuid4()}/", headers=admin_headers)
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

    async def test_create_unauthenticated(self, async_client: AsyncClient):
        """POST /v1/inventory/locations/ - No auth is rejected."""
        response = await async_client.post("/v1/inventory/locations/", json={"name": "New Warehouse"})
        assert response.status_code == 401

    async def test_update_not_found(self, async_client: AsyncClient, admin_headers):
        """PATCH /v1/inventory/locations/{id} - Unknown ID returns 404."""
        response = await async_client.patch(f"/v1/inventory/locations/{uuid4()}/",
            headers=admin_headers, json={"name": "Nowhere"}
        )
        assert response.status_code == 404

    async def test_delete_not_found(self, async_client: AsyncClient, admin_headers):
        """DELETE /v1/inventory/locations/{id} - Unknown ID returns 404."""
        response = await async_client.delete(f"/v1/inventory/locations/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_delete_with_existing_inventory_rejected(self, async_client: AsyncClient, admin_headers,
                                                              created_location, created_variant):
        """DELETE /v1/inventory/locations/{id} - Location still holding inventory can't be deleted."""
        listed = await async_client.get(f"/v1/inventory/?product_id={created_variant['product_id']}", headers=admin_headers)
        inventory_id = listed.json()["data"][0]["id"]
        await async_client.patch(f"/v1/inventory/{inventory_id}/",
            headers=admin_headers, json={"location_id": created_location["id"]}
        )

        response = await async_client.delete(f"/v1/inventory/locations/{created_location['id']}/", headers=admin_headers)
        assert response.status_code == 400

    async def test_update_name_to_null_is_a_server_error(self, async_client: AsyncClient, admin_headers, created_location):
        """PATCH /v1/inventory/locations/{id} - name is NOT NULL at the DB level but the update
        schema allows an explicit null (only "unset" fields are excluded); the resulting
        constraint violation is a real, un-mocked way to exercise the endpoint's generic
        exception handler (a raw DB error, not one of the service's deliberate APIExceptions)."""
        response = await async_client.patch(f"/v1/inventory/locations/{created_location['id']}/",
            headers=admin_headers, json={"name": None}
        )
        assert response.status_code == 500


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

    async def test_get_by_id(self, async_client: AsyncClient, admin_headers, created_variant):
        """GET /v1/inventory/{id} - Get a specific inventory row by its own id."""
        listed = await async_client.get(f"/v1/inventory/?product_id={created_variant['product_id']}", headers=admin_headers)
        inventory_id = listed.json()["data"][0]["id"]

        response = await async_client.get(f"/v1/inventory/{inventory_id}/", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["data"]["id"] == inventory_id

    async def test_get_by_id_not_found(self, async_client: AsyncClient, admin_headers):
        """GET /v1/inventory/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/inventory/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_update_as_admin(self, async_client: AsyncClient, admin_headers, created_variant):
        """PATCH /v1/inventory/{id} - Update quantity/threshold (admin)."""
        listed = await async_client.get(f"/v1/inventory/?product_id={created_variant['product_id']}", headers=admin_headers)
        inventory_id = listed.json()["data"][0]["id"]

        response = await async_client.patch(f"/v1/inventory/{inventory_id}/",
            headers=admin_headers, json={"quantity": 42, "low_stock_threshold": 5})
        assert response.status_code == 200

    async def test_update_requires_admin(self, async_client: AsyncClient, auth_headers, admin_headers, created_variant):
        """PATCH /v1/inventory/{id} - Non-admin is forbidden."""
        listed = await async_client.get(f"/v1/inventory/?product_id={created_variant['product_id']}", headers=admin_headers)
        inventory_id = listed.json()["data"][0]["id"]

        response = await async_client.patch(f"/v1/inventory/{inventory_id}/",
            headers=auth_headers, json={"quantity": 1})
        assert response.status_code == 403

    async def test_delete_as_admin(self, async_client: AsyncClient, admin_headers, created_variant):
        """DELETE /v1/inventory/{id} - Delete an inventory row (admin)."""
        listed = await async_client.get(f"/v1/inventory/?product_id={created_variant['product_id']}", headers=admin_headers)
        inventory_id = listed.json()["data"][0]["id"]

        response = await async_client.delete(f"/v1/inventory/{inventory_id}/", headers=admin_headers)
        assert response.status_code == 200

        get_after = await async_client.get(f"/v1/inventory/{inventory_id}/", headers=admin_headers)
        assert get_after.status_code == 404

    async def test_delete_not_found(self, async_client: AsyncClient, admin_headers):
        """DELETE /v1/inventory/{id} - Unknown ID returns 404."""
        response = await async_client.delete(f"/v1/inventory/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_create_fresh_inventory(self, async_client: AsyncClient, admin_headers, created_variant, created_location):
        """POST /v1/inventory/ - Creating inventory for a variant with none yet succeeds."""
        listed = await async_client.get(f"/v1/inventory/?product_id={created_variant['product_id']}", headers=admin_headers)
        inventory_id = listed.json()["data"][0]["id"]
        await async_client.delete(f"/v1/inventory/{inventory_id}/", headers=admin_headers)

        response = await async_client.post("/v1/inventory/", headers=admin_headers, json={
            "variant_id": created_variant["id"], "location_id": created_location["id"], "quantity": 33
        })
        assert response.status_code == 201
        assert response.json()["data"]["quantity_available"] == 33
        assert response.json()["data"]["location"]["id"] == created_location["id"]

    async def test_create_unknown_variant_returns_404(self, async_client: AsyncClient, admin_headers, created_location):
        """POST /v1/inventory/ - Unknown variant_id returns 404."""
        response = await async_client.post("/v1/inventory/", headers=admin_headers, json={
            "variant_id": str(uuid4()), "location_id": created_location["id"], "quantity": 10
        })
        assert response.status_code == 404

    async def test_create_unknown_location_is_a_server_error(self, async_client: AsyncClient, admin_headers, created_variant):
        """POST /v1/inventory/ - The service validates variant_id but not location_id; a
        location_id with no matching row is a real (un-mocked) way to trigger a foreign-key
        violation on commit, exercising the endpoint's generic exception handler."""
        listed = await async_client.get(f"/v1/inventory/?product_id={created_variant['product_id']}", headers=admin_headers)
        inventory_id = listed.json()["data"][0]["id"]
        await async_client.delete(f"/v1/inventory/{inventory_id}/", headers=admin_headers)

        response = await async_client.post("/v1/inventory/", headers=admin_headers, json={
            "variant_id": created_variant["id"], "location_id": str(uuid4()), "quantity": 5
        })
        assert response.status_code == 500

    async def test_update_not_found(self, async_client: AsyncClient, admin_headers):
        """PATCH /v1/inventory/{id} - Unknown ID returns 404."""
        response = await async_client.patch(f"/v1/inventory/{uuid4()}/", headers=admin_headers, json={"quantity": 1})
        assert response.status_code == 404

    async def test_update_with_unknown_location_id_is_a_server_error(self, async_client: AsyncClient, admin_headers, created_variant):
        """PATCH /v1/inventory/{id} - Directly setting location_id (as opposed to
        location_name) skips the get-or-create lookup entirely, so a non-existent location_id
        reaches the DB as a real foreign-key violation."""
        listed = await async_client.get(f"/v1/inventory/?product_id={created_variant['product_id']}", headers=admin_headers)
        inventory_id = listed.json()["data"][0]["id"]

        response = await async_client.patch(f"/v1/inventory/{inventory_id}/",
            headers=admin_headers, json={"location_id": str(uuid4())})
        assert response.status_code == 500

    async def test_list_filters(self, async_client: AsyncClient, admin_headers, created_variant):
        """GET /v1/inventory/ - in_stock/out_of_stock/search/location_name/sort_by all return 200."""
        for query in (
            "in_stock=true", "in_stock=false", "out_of_stock=true", "out_of_stock=false",
            f"search={created_variant['sku']}", "location_name=Nowhere",
            "sort_by=quantity&sort_order=desc",
        ):
            response = await async_client.get(f"/v1/inventory/?{query}", headers=admin_headers)
            assert response.status_code == 200, query


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

    async def test_create_insufficient_stock_returns_400(self, async_client: AsyncClient, admin_headers, created_variant):
        """POST /v1/inventory/adjustments/ - Reducing below zero is rejected (would oversell)."""
        response = await async_client.post("/v1/inventory/adjustments/", headers=admin_headers, json={
            "variant_id": created_variant["id"], "quantity_change": -(created_variant["stock"] + 1), "reason": "Sold"
        })
        assert response.status_code == 400

    async def test_create_unknown_variant_returns_404(self, async_client: AsyncClient, admin_headers):
        """POST /v1/inventory/adjustments/ - Unknown variant_id returns 404."""
        response = await async_client.post("/v1/inventory/adjustments/", headers=admin_headers, json={
            "variant_id": str(uuid4()), "quantity_change": 1, "reason": "Restock"
        })
        assert response.status_code == 404

    async def test_list_requires_admin(self, async_client: AsyncClient, auth_headers):
        """GET /v1/inventory/adjustments/ - Non-admin is forbidden."""
        response = await async_client.get("/v1/inventory/adjustments/", headers=auth_headers)
        assert response.status_code == 403

    async def test_list_as_admin(self, async_client: AsyncClient, admin_headers):
        """GET /v1/inventory/adjustments/ - Admin can list adjustments."""
        response = await async_client.get("/v1/inventory/adjustments/", headers=admin_headers)
        assert response.status_code == 200

    async def test_get_by_id(self, async_client: AsyncClient, admin_headers, created_variant):
        """GET /v1/inventory/adjustments/{id} - Get a specific adjustment."""
        await async_client.post("/v1/inventory/adjustments/", headers=admin_headers, json={
            "variant_id": created_variant["id"], "quantity_change": 5, "reason": "Restock"
        })
        listed = await async_client.get("/v1/inventory/adjustments/", headers=admin_headers)
        adjustment_id = listed.json()["data"][0]["id"]

        response = await async_client.get(f"/v1/inventory/adjustments/{adjustment_id}/", headers=admin_headers)
        assert response.status_code == 200

    async def test_get_by_id_not_found(self, async_client: AsyncClient, admin_headers):
        """GET /v1/inventory/adjustments/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/inventory/adjustments/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_delete_as_admin(self, async_client: AsyncClient, admin_headers, created_variant):
        """DELETE /v1/inventory/adjustments/{id} - Delete an adjustment (admin)."""
        await async_client.post("/v1/inventory/adjustments/", headers=admin_headers, json={
            "variant_id": created_variant["id"], "quantity_change": 5, "reason": "Restock"
        })
        listed = await async_client.get("/v1/inventory/adjustments/", headers=admin_headers)
        adjustment_id = listed.json()["data"][0]["id"]

        response = await async_client.delete(f"/v1/inventory/adjustments/{adjustment_id}/", headers=admin_headers)
        assert response.status_code == 200

    async def test_delete_not_found(self, async_client: AsyncClient, admin_headers):
        """DELETE /v1/inventory/adjustments/{id} - Unknown ID returns 404."""
        response = await async_client.delete(f"/v1/inventory/adjustments/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_get_requires_admin(self, async_client: AsyncClient, auth_headers):
        """GET /v1/inventory/adjustments/{id} - Non-admin is forbidden."""
        response = await async_client.get(f"/v1/inventory/adjustments/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 403

    async def test_delete_requires_admin(self, async_client: AsyncClient, auth_headers):
        """DELETE /v1/inventory/adjustments/{id} - Non-admin is forbidden."""
        response = await async_client.delete(f"/v1/inventory/adjustments/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 403

    async def test_list_filtered_by_inventory_id(self, async_client: AsyncClient, admin_headers, created_variant):
        """GET /v1/inventory/adjustments/?inventory_id= - Filter adjustments to one inventory row."""
        await async_client.post("/v1/inventory/adjustments/", headers=admin_headers, json={
            "variant_id": created_variant["id"], "quantity_change": 5, "reason": "Restock"
        })
        listed = await async_client.get(f"/v1/inventory/?product_id={created_variant['product_id']}", headers=admin_headers)
        inventory_id = listed.json()["data"][0]["id"]

        response = await async_client.get(f"/v1/inventory/adjustments/?inventory_id={inventory_id}", headers=admin_headers)
        assert response.status_code == 200
        assert all(a["inventory_id"] == inventory_id for a in response.json()["data"])


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

    async def test_sync_all_requires_admin(self, async_client: AsyncClient, auth_headers):
        """POST /v1/inventory/sync-all/ - Non-admin is forbidden."""
        response = await async_client.post("/v1/inventory/sync-all/", headers=auth_headers)
        assert response.status_code == 403

    async def test_sync_product_requires_admin(self, async_client: AsyncClient, auth_headers, created_variant):
        """POST /v1/inventory/sync/product/{id}/ - Non-admin is forbidden."""
        response = await async_client.post(
            f"/v1/inventory/sync/product/{created_variant['product_id']}/", headers=auth_headers
        )
        assert response.status_code == 403
