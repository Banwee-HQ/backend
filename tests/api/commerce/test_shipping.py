"""Tests for api/commerce/shipping.py - /v1/shipping endpoints (methods + cost calculation).

Shipment tracking, carriers, and providers live under /v1/shipping-tracking/
instead - see test_shipping_tracking.py.
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.fixture
async def created_method(async_client: AsyncClient, admin_headers):
    response = await async_client.post("/v1/shipping/methods/", headers=admin_headers, json={
        "name": f"Express-{uuid4().hex[:6]}", "price": 15.0, "estimated_days": 2
    })
    return response.json()["data"]


@pytest.mark.api
@pytest.mark.shipping
class TestShippingMethodEndpoints:

    async def test_list_public(self, async_client: AsyncClient, created_method):
        """GET /v1/shipping/methods - No auth required, returns active methods."""
        response = await async_client.get("/v1/shipping/methods/")
        assert response.status_code == 200

    async def test_list_all_requires_admin(self, async_client: AsyncClient, auth_headers):
        """GET /v1/shipping/methods?all_methods=true - Non-admin is forbidden."""
        response = await async_client.get("/v1/shipping/methods/?all_methods=true", headers=auth_headers)
        assert response.status_code == 403

    async def test_list_all_requires_auth(self, async_client: AsyncClient):
        """GET /v1/shipping/methods?all_methods=true - Anonymous is rejected."""
        response = await async_client.get("/v1/shipping/methods/?all_methods=true")
        assert response.status_code == 401

    async def test_list_all_as_admin(self, async_client: AsyncClient, admin_headers, created_method):
        """GET /v1/shipping/methods?all_methods=true - Admin sees all methods, paginated."""
        response = await async_client.get("/v1/shipping/methods/?all_methods=true", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["pagination"]["total"] >= 1

    async def test_create_as_admin(self, async_client: AsyncClient, admin_headers):
        """POST /v1/shipping/methods - Create shipping method (admin)."""
        response = await async_client.post("/v1/shipping/methods/", headers=admin_headers, json={
            "name": f"Overnight-{uuid4().hex[:6]}", "price": 25.0, "estimated_days": 1
        })
        assert response.status_code == 201

    async def test_create_requires_admin(self, async_client: AsyncClient, auth_headers):
        """POST /v1/shipping/methods - Non-admin is forbidden."""
        response = await async_client.post("/v1/shipping/methods/", headers=auth_headers, json={
            "name": "Sneaky", "price": 1.0, "estimated_days": 1
        })
        assert response.status_code == 403

    async def test_create_unauthenticated(self, async_client: AsyncClient):
        """POST /v1/shipping/methods - No auth is rejected."""
        response = await async_client.post("/v1/shipping/methods/", json={
            "name": "Sneaky", "price": 1.0, "estimated_days": 1
        })
        assert response.status_code == 401

    async def test_list_all_filters_by_active(self, async_client: AsyncClient, admin_headers, created_method):
        """GET /v1/shipping/methods?all_methods=true&is_active=false - Filter to inactive methods only."""
        await async_client.patch(f"/v1/shipping/methods/{created_method['id']}/",
            headers=admin_headers, json={"is_active": False}
        )
        response = await async_client.get(
            "/v1/shipping/methods/?all_methods=true&is_active=false", headers=admin_headers
        )
        assert response.status_code == 200
        ids = [m["id"] for m in response.json()["data"]]
        assert created_method["id"] in ids

    async def test_update_not_found(self, async_client: AsyncClient, admin_headers):
        response = await async_client.patch(f"/v1/shipping/methods/{uuid4()}/",
            headers=admin_headers, json={"price": 5.0}
        )
        assert response.status_code == 404

    async def test_get_by_id(self, async_client: AsyncClient, created_method):
        """GET /v1/shipping/methods/{id} - Get a method (no auth required)."""
        response = await async_client.get(f"/v1/shipping/methods/{created_method['id']}/")
        assert response.status_code == 200

    async def test_get_by_id_not_found(self, async_client: AsyncClient):
        """GET /v1/shipping/methods/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/shipping/methods/{uuid4()}/")
        assert response.status_code == 404

    async def test_update_as_admin(self, async_client: AsyncClient, admin_headers, created_method):
        """PATCH /v1/shipping/methods/{id} - Update method (admin)."""
        response = await async_client.patch(f"/v1/shipping/methods/{created_method['id']}/",
            headers=admin_headers, json={"price": 20.0}
        )
        assert response.status_code == 200
        assert response.json()["data"]["price"] == 20.0

    async def test_update_requires_admin(self, async_client: AsyncClient, auth_headers, created_method):
        """PATCH /v1/shipping/methods/{id} - Non-admin is forbidden."""
        response = await async_client.patch(f"/v1/shipping/methods/{created_method['id']}/",
            headers=auth_headers, json={"price": 1.0}
        )
        assert response.status_code == 403

    async def test_delete_as_admin(self, async_client: AsyncClient, admin_headers, created_method):
        """DELETE /v1/shipping/methods/{id} - Delete method (admin)."""
        response = await async_client.delete(f"/v1/shipping/methods/{created_method['id']}/", headers=admin_headers)
        assert response.status_code == 200

    async def test_delete_requires_admin(self, async_client: AsyncClient, auth_headers, created_method):
        """DELETE /v1/shipping/methods/{id} - Non-admin is forbidden."""
        response = await async_client.delete(f"/v1/shipping/methods/{created_method['id']}/", headers=auth_headers)
        assert response.status_code == 403


@pytest.mark.api
@pytest.mark.shipping
class TestCalculateShippingCost:

    async def test_calculate_with_method(self, async_client: AsyncClient, created_method):
        """POST /v1/shipping/calculate - Calculate cost using a specific method."""
        response = await async_client.post("/v1/shipping/calculate/", json={
            "order_amount": 50.0, "shipping_method_id": created_method["id"], "destination_country": "US"
        })
        assert response.status_code == 200
        assert response.json()["data"]["shipping_cost"] == created_method["price"]

    async def test_calculate_without_method(self, async_client: AsyncClient):
        """POST /v1/shipping/calculate - Calculate cost with no method specified falls back gracefully."""
        response = await async_client.post("/v1/shipping/calculate/", json={
            "order_amount": 50.0, "destination_country": "US"
        })
        assert response.status_code == 200
