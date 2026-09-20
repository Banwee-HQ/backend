"""Tests for api/commerce/shipping_tracking.py - /v1/shipping-tracking endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from models.commerce.orders import Order, OrderStatus, PaymentStatus, FulfillmentStatus
from core.utils.uuid_utils import uuid7


@pytest.fixture
async def created_carrier(async_client: AsyncClient, admin_headers):
    response = await async_client.post("/v1/shipping-tracking/carriers/", headers=admin_headers, json={
        "code": f"tc{uuid4().hex[:6]}", "name": "Test Carrier"
    })
    return response.json()["data"]


@pytest.fixture
async def created_provider(async_client: AsyncClient, admin_headers, created_carrier):
    response = await async_client.post("/v1/shipping-tracking/providers/", headers=admin_headers, json={
        "name": "Test Provider", "carrier": created_carrier["code"],
        "api_url": "https://example.com/api",
        "tracking_url_template": "https://example.com/track/{tracking_number}",
    })
    return response.json()["data"]


@pytest.fixture
async def own_order(db_session: AsyncSession, test_user) -> Order:
    order = Order(
        id=uuid7(), order_number=f"ORD-{uuid4().hex[:10].upper()}", user_id=test_user.id,
        order_status=OrderStatus.CONFIRMED, payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.UNFULFILLED,
        subtotal=39.98, shipping_cost=10.0, tax_amount=0.0, total_amount=49.98,
        billing_address={"street": "1 Test St"}, shipping_address={"street": "1 Test St"},
    )
    db_session.add(order)
    await db_session.commit()
    return order


@pytest.fixture
async def created_shipment(async_client: AsyncClient, auth_headers, created_provider, own_order):
    response = await async_client.post("/v1/shipping-tracking/shipments/", headers=auth_headers, json={
        "order_id": str(own_order.id), "carrier": created_provider["carrier"],
        "tracking_number": f"TRACK{uuid4().hex[:8]}",
    })
    return response.json()["data"]


@pytest.mark.api
@pytest.mark.shipping
class TestCarrierEndpoints:

    async def test_list_public(self, async_client: AsyncClient, created_carrier):
        """GET /v1/shipping-tracking/carriers - Public, no auth required."""
        response = await async_client.get("/v1/shipping-tracking/carriers/")
        assert response.status_code == 200

    async def test_create_as_admin(self, async_client: AsyncClient, admin_headers):
        """POST /v1/shipping-tracking/carriers - Create carrier (admin)."""
        response = await async_client.post("/v1/shipping-tracking/carriers/", headers=admin_headers, json={
            "code": f"nc{uuid4().hex[:6]}", "name": "New Carrier"
        })
        assert response.status_code == 200

    async def test_create_requires_admin(self, async_client: AsyncClient, auth_headers):
        """POST /v1/shipping-tracking/carriers - Non-admin is forbidden."""
        response = await async_client.post("/v1/shipping-tracking/carriers/", headers=auth_headers, json={
            "code": "sneaky", "name": "Sneaky"
        })
        assert response.status_code == 403

    async def test_update_as_admin(self, async_client: AsyncClient, admin_headers, created_carrier):
        """PATCH /v1/shipping-tracking/carriers/{id} - Update carrier (admin)."""
        response = await async_client.patch(f"/v1/shipping-tracking/carriers/{created_carrier['id']}/",
            headers=admin_headers, json={"name": "Renamed Carrier"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Renamed Carrier"

    async def test_delete_as_admin(self, async_client: AsyncClient, admin_headers, created_carrier):
        """DELETE /v1/shipping-tracking/carriers/{id} - Delete an unused carrier (admin)."""
        response = await async_client.delete(f"/v1/shipping-tracking/carriers/{created_carrier['id']}/", headers=admin_headers)
        assert response.status_code == 200

    async def test_delete_with_provider_blocked(self, async_client: AsyncClient, admin_headers, created_provider, created_carrier):
        """DELETE /v1/shipping-tracking/carriers/{id} - Blocked while a provider references it."""
        response = await async_client.delete(f"/v1/shipping-tracking/carriers/{created_carrier['id']}/", headers=admin_headers)
        assert response.status_code == 400


@pytest.mark.api
@pytest.mark.shipping
class TestProviderEndpoints:

    async def test_create_as_admin(self, async_client: AsyncClient, admin_headers, created_carrier):
        """POST /v1/shipping-tracking/providers - Create provider (admin)."""
        response = await async_client.post("/v1/shipping-tracking/providers/", headers=admin_headers, json={
            "name": "Another Provider", "carrier": created_carrier["code"],
            "api_url": "https://example.com/api", "tracking_url_template": "https://example.com/t/{tracking_number}",
        })
        assert response.status_code == 200

    async def test_create_unknown_carrier(self, async_client: AsyncClient, admin_headers):
        """POST /v1/shipping-tracking/providers - Unknown carrier code returns 404."""
        response = await async_client.post("/v1/shipping-tracking/providers/", headers=admin_headers, json={
            "name": "Provider", "carrier": "nope-not-real",
            "api_url": "https://example.com/api", "tracking_url_template": "https://example.com/t",
        })
        assert response.status_code == 404

    async def test_create_requires_admin(self, async_client: AsyncClient, auth_headers, created_carrier):
        """POST /v1/shipping-tracking/providers - Non-admin is forbidden."""
        response = await async_client.post("/v1/shipping-tracking/providers/", headers=auth_headers, json={
            "name": "Provider", "carrier": created_carrier["code"],
            "api_url": "https://example.com/api", "tracking_url_template": "https://example.com/t",
        })
        assert response.status_code == 403

    async def test_list_requires_admin(self, async_client: AsyncClient, auth_headers):
        """GET /v1/shipping-tracking/providers - Non-admin is forbidden."""
        response = await async_client.get("/v1/shipping-tracking/providers/", headers=auth_headers)
        assert response.status_code == 403

    async def test_list_as_admin(self, async_client: AsyncClient, admin_headers, created_provider):
        """GET /v1/shipping-tracking/providers - Admin can list providers."""
        response = await async_client.get("/v1/shipping-tracking/providers/", headers=admin_headers)
        assert response.status_code == 200

    async def test_update_as_admin(self, async_client: AsyncClient, admin_headers, created_provider):
        """PATCH /v1/shipping-tracking/providers/{id} - Update provider (admin)."""
        response = await async_client.patch(f"/v1/shipping-tracking/providers/{created_provider['id']}/",
            headers=admin_headers, json={"is_active": False}
        )
        assert response.status_code == 200
        assert response.json()["data"]["is_active"] is False

    async def test_delete_as_admin(self, async_client: AsyncClient, admin_headers, created_provider):
        """DELETE /v1/shipping-tracking/providers/{id} - Delete provider (admin)."""
        response = await async_client.delete(f"/v1/shipping-tracking/providers/{created_provider['id']}/", headers=admin_headers)
        assert response.status_code == 200


@pytest.mark.api
@pytest.mark.shipping
class TestShipmentEndpoints:

    async def test_create(self, async_client: AsyncClient, auth_headers, created_provider, own_order):
        """POST /v1/shipping-tracking/shipments - Create a shipment for a real order."""
        response = await async_client.post("/v1/shipping-tracking/shipments/", headers=auth_headers, json={
            "order_id": str(own_order.id), "carrier": created_provider["carrier"],
            "tracking_number": f"TRACK{uuid4().hex[:8]}",
        })
        assert response.status_code == 200
        assert response.json()["data"]["order_id"] == str(own_order.id)

    async def test_create_unknown_carrier(self, async_client: AsyncClient, auth_headers, own_order):
        """POST /v1/shipping-tracking/shipments - Unknown carrier is rejected."""
        response = await async_client.post("/v1/shipping-tracking/shipments/", headers=auth_headers, json={
            "order_id": str(own_order.id), "carrier": "not-a-real-carrier",
            "tracking_number": "TRACK123",
        })
        assert response.status_code == 400

    async def test_get_by_id(self, async_client: AsyncClient, auth_headers, created_shipment):
        """GET /v1/shipping-tracking/shipments/{id} - Get a shipment."""
        response = await async_client.get(f"/v1/shipping-tracking/shipments/{created_shipment['id']}/", headers=auth_headers)
        assert response.status_code == 200

    async def test_get_by_id_not_found(self, async_client: AsyncClient, auth_headers):
        """GET /v1/shipping-tracking/shipments/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/shipping-tracking/shipments/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 404

    async def test_list_own(self, async_client: AsyncClient, auth_headers, created_shipment):
        """GET /v1/shipping-tracking/shipments - List own shipments."""
        response = await async_client.get("/v1/shipping-tracking/shipments/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["pagination"]["total"] >= 1

    async def test_update_status(self, async_client: AsyncClient, auth_headers, created_shipment):
        """PATCH /v1/shipping-tracking/shipments/{id}/status - Update tracking status."""
        response = await async_client.patch(f"/v1/shipping-tracking/shipments/{created_shipment['id']}/status/",
            headers=auth_headers, json={"status": "in_transit", "event_description": "Left warehouse"}
        )
        assert response.status_code == 200

    async def test_track(self, async_client: AsyncClient, auth_headers, created_shipment):
        """POST /v1/shipping-tracking/track - Track a shipment via carrier integration."""
        response = await async_client.post("/v1/shipping-tracking/track/", headers=auth_headers, json={
            "tracking_number": created_shipment["tracking_number"], "carrier": created_shipment["carrier"]
        })
        assert response.status_code in [200, 400]


@pytest.mark.api
@pytest.mark.shipping
class TestWebhookEndpoint:

    async def test_handle_webhook(self, async_client: AsyncClient):
        """POST /v1/shipping-tracking/webhooks/{carrier} - No auth required."""
        response = await async_client.post("/v1/shipping-tracking/webhooks/ups/", json={"event": "delivered"})
        assert response.status_code == 200
