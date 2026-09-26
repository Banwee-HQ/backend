"""Tests for api/commerce/shipping_tracking.py - /v1/shipping-tracking endpoints."""

import pytest
from contextlib import asynccontextmanager
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

import core.db as core_db
from core.exceptions import APIException
from core.utils.uuid_utils import uuid7
from models.commerce.orders import Order, OrderStatus, PaymentStatus, FulfillmentStatus


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
async def created_shipment(async_client: AsyncClient, admin_headers, created_provider, own_order):
    response = await async_client.post("/v1/shipping-tracking/shipments/", headers=admin_headers, json={
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

    async def test_create_duplicate_code_is_rejected(self, async_client: AsyncClient, admin_headers):
        """"ups" is pre-seeded (see the initial schema migration) - a real unique-code
        collision, not a mocked one."""
        response = await async_client.post("/v1/shipping-tracking/carriers/", headers=admin_headers, json={
            "code": "ups", "name": "Duplicate UPS"
        })
        assert response.status_code == 400

    async def test_create_propagates_http_exception(self, async_client: AsyncClient, admin_headers, mocker):
        mocker.patch(
            "services.commerce.carriers.CarrierService.create",
            side_effect=HTTPException(status_code=403, detail="nope"),
        )
        response = await async_client.post("/v1/shipping-tracking/carriers/", headers=admin_headers, json={
            "code": f"x{uuid4().hex[:6]}", "name": "X"
        })
        assert response.status_code == 403

    async def test_create_with_code_exceeding_db_column_returns_500(self, async_client: AsyncClient, admin_headers):
        """code is a plain `str` in the schema but VARCHAR(50) in the DB - an
        over-length value is a real DB error, not a mocked one."""
        response = await async_client.post("/v1/shipping-tracking/carriers/", headers=admin_headers, json={
            "code": "x" * 60, "name": "Too Long"
        })
        assert response.status_code == 500

    async def test_update_unknown_id_returns_404(self, async_client: AsyncClient, admin_headers):
        response = await async_client.patch(f"/v1/shipping-tracking/carriers/{uuid4()}/",
            headers=admin_headers, json={"name": "Nope"}
        )
        assert response.status_code == 404

    async def test_update_propagates_api_exception(self, async_client: AsyncClient, admin_headers, created_carrier, mocker):
        mocker.patch(
            "services.commerce.carriers.CarrierService.update",
            side_effect=APIException(status_code=400, message="bad update"),
        )
        response = await async_client.patch(f"/v1/shipping-tracking/carriers/{created_carrier['id']}/",
            headers=admin_headers, json={"name": "X"}
        )
        assert response.status_code == 400

    async def test_update_with_name_exceeding_db_column_returns_500(self, async_client: AsyncClient, admin_headers, created_carrier):
        response = await async_client.patch(f"/v1/shipping-tracking/carriers/{created_carrier['id']}/",
            headers=admin_headers, json={"name": "x" * 150}
        )
        assert response.status_code == 500

    async def test_delete_unknown_id_returns_404(self, async_client: AsyncClient, admin_headers):
        response = await async_client.delete(f"/v1/shipping-tracking/carriers/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_delete_wraps_unexpected_error_as_500(self, async_client: AsyncClient, admin_headers, created_carrier, mocker):
        mocker.patch(
            "services.commerce.carriers.CarrierService.delete",
            side_effect=RuntimeError("db down"),
        )
        response = await async_client.delete(f"/v1/shipping-tracking/carriers/{created_carrier['id']}/", headers=admin_headers)
        assert response.status_code == 500

    async def test_list_wraps_unexpected_error_as_500(self, async_client: AsyncClient, mocker):
        mocker.patch(
            "services.commerce.carriers.CarrierService.list",
            side_effect=RuntimeError("db down"),
        )
        response = await async_client.get("/v1/shipping-tracking/carriers/")
        assert response.status_code == 500


@pytest.mark.api
@pytest.mark.shipping
class TestProviderEndpoints:

    async def test_patch_ignores_non_editable_fields(self, async_client: AsyncClient, admin_headers, created_provider):
        """PATCH /v1/shipping-tracking/providers/{id} - ids and timestamps can't be overwritten."""
        response = await async_client.patch(f"/v1/shipping-tracking/providers/{created_provider['id']}/",
            headers=admin_headers, json={"name": "Renamed", "created_at": "2000-01-01T00:00:00+00:00", "id": "x"})
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "Renamed"
        assert data["id"] == created_provider["id"]
        assert data["created_at"] == created_provider["created_at"]

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

    async def test_create_missing_required_key_returns_500(self, async_client: AsyncClient, admin_headers, created_carrier):
        """provider_data is a raw dict (no pydantic schema) - a missing required key
        is a real KeyError, not a mocked failure, and must roll back cleanly."""
        response = await async_client.post("/v1/shipping-tracking/providers/", headers=admin_headers, json={
            "name": "Incomplete Provider", "carrier": created_carrier["code"],
            "api_url": "https://example.com/api",
            # tracking_url_template intentionally omitted
        })
        assert response.status_code == 500

    async def test_list_wraps_unexpected_error_as_500(self, async_client: AsyncClient, admin_headers, mocker):
        mocker.patch("api.commerce.shipping_tracking.APIResponse.success", side_effect=RuntimeError("boom"))
        response = await async_client.get("/v1/shipping-tracking/providers/", headers=admin_headers)
        assert response.status_code == 500

    async def test_update_unknown_id_returns_404(self, async_client: AsyncClient, admin_headers):
        response = await async_client.patch(f"/v1/shipping-tracking/providers/{uuid4()}/",
            headers=admin_headers, json={"is_active": False}
        )
        assert response.status_code == 404

    async def test_update_reassigns_carrier_by_code(self, async_client: AsyncClient, admin_headers, created_provider):
        """The 'carrier' field on update is a carrier CODE, resolved to carrier_id."""
        new_carrier_resp = await async_client.post("/v1/shipping-tracking/carriers/", headers=admin_headers, json={
            "code": f"nc{uuid4().hex[:6]}", "name": "New Carrier For Reassign"
        })
        new_carrier = new_carrier_resp.json()["data"]
        response = await async_client.patch(f"/v1/shipping-tracking/providers/{created_provider['id']}/",
            headers=admin_headers, json={"carrier": new_carrier["code"]}
        )
        assert response.status_code == 200
        assert response.json()["data"]["carrier"] == new_carrier["code"]

    async def test_update_unknown_carrier_code_returns_404(self, async_client: AsyncClient, admin_headers, created_provider):
        response = await async_client.patch(f"/v1/shipping-tracking/providers/{created_provider['id']}/",
            headers=admin_headers, json={"carrier": "not-a-real-carrier"}
        )
        assert response.status_code == 404

    async def test_update_with_name_exceeding_db_column_returns_500(self, async_client: AsyncClient, admin_headers, created_provider):
        response = await async_client.patch(f"/v1/shipping-tracking/providers/{created_provider['id']}/",
            headers=admin_headers, json={"name": "x" * 150}
        )
        assert response.status_code == 500

    async def test_delete_unknown_id_returns_404(self, async_client: AsyncClient, admin_headers):
        response = await async_client.delete(f"/v1/shipping-tracking/providers/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_delete_referenced_by_shipment_keeps_the_shipment(self, async_client: AsyncClient, admin_headers, created_shipment, created_provider):
        """Deleting a provider detaches its shipments instead of deleting them."""
        response = await async_client.delete(f"/v1/shipping-tracking/providers/{created_provider['id']}/", headers=admin_headers)
        assert response.status_code == 200
        shipment = await async_client.get(f"/v1/shipping-tracking/shipments/{created_shipment['id']}/", headers=admin_headers)
        assert shipment.status_code == 200


@pytest.mark.api
@pytest.mark.shipping
class TestShipmentEndpoints:

    async def test_create(self, async_client: AsyncClient, admin_headers, created_provider, own_order):
        """POST /v1/shipping-tracking/shipments - Create a shipment for a real order."""
        response = await async_client.post("/v1/shipping-tracking/shipments/", headers=admin_headers, json={
            "order_id": str(own_order.id), "carrier": created_provider["carrier"],
            "tracking_number": f"TRACK{uuid4().hex[:8]}",
        })
        assert response.status_code == 200
        assert response.json()["data"]["order_id"] == str(own_order.id)

    async def test_unpaid_order_cannot_be_shipped(self, async_client: AsyncClient, admin_headers, created_carrier, own_order, db_session: AsyncSession):
        own_order.payment_status = PaymentStatus.PENDING
        own_order.order_status = OrderStatus.PENDING
        await db_session.commit()
        response = await async_client.post("/v1/shipping-tracking/shipments/", headers=admin_headers, json={
            "order_id": str(own_order.id), "carrier": created_carrier["code"], "tracking_number": f"TRACK{uuid4().hex[:8]}",
        })
        assert response.status_code == 400

    async def test_create_without_provider(self, async_client: AsyncClient, admin_headers, created_carrier, own_order):
        """A carrier with no API account still takes manual shipments."""
        response = await async_client.post("/v1/shipping-tracking/shipments/", headers=admin_headers, json={
            "order_id": str(own_order.id), "carrier": created_carrier["code"],
            "tracking_number": f"TRACK{uuid4().hex[:8]}",
        })
        assert response.status_code == 200

    async def test_create_unknown_carrier(self, async_client: AsyncClient, admin_headers, own_order):
        """POST /v1/shipping-tracking/shipments - Unknown carrier is rejected."""
        response = await async_client.post("/v1/shipping-tracking/shipments/", headers=admin_headers, json={
            "order_id": str(own_order.id), "carrier": "not-a-real-carrier",
            "tracking_number": "TRACK123",
        })
        assert response.status_code == 400

    async def test_create_with_order_item_id(self, async_client: AsyncClient, admin_headers, created_provider, own_order):
        """order_id and order_item_id are both plain `str` fields converted to UUID by
        hand in the router (schemas/commerce/shipping_tracking.py has no UUID type) -
        a syntactically valid but non-existent order_item_id is a real FK violation."""
        response = await async_client.post("/v1/shipping-tracking/shipments/", headers=admin_headers, json={
            "order_id": str(own_order.id), "carrier": created_provider["carrier"],
            "tracking_number": f"TRACK{uuid4().hex[:8]}", "order_item_id": str(uuid4()),
        })
        assert response.status_code == 500

    async def test_create_with_malformed_order_id_returns_500(self, async_client: AsyncClient, admin_headers, created_provider):
        response = await async_client.post("/v1/shipping-tracking/shipments/", headers=admin_headers, json={
            "order_id": "not-a-valid-uuid", "carrier": created_provider["carrier"],
            "tracking_number": f"TRACK{uuid4().hex[:8]}",
        })
        assert response.status_code == 500

    async def test_create_propagates_http_exception(self, async_client: AsyncClient, admin_headers, own_order, mocker):
        mocker.patch(
            "services.commerce.shipping_tracking.ShippingTrackingService.create",
            side_effect=HTTPException(status_code=403, detail="nope"),
        )
        response = await async_client.post("/v1/shipping-tracking/shipments/", headers=admin_headers, json={
            "order_id": str(own_order.id), "carrier": "ups", "tracking_number": "TRACK123",
        })
        assert response.status_code == 403

    async def test_get_by_id(self, async_client: AsyncClient, auth_headers, created_shipment):
        """GET /v1/shipping-tracking/shipments/{id} - Get a shipment."""
        response = await async_client.get(f"/v1/shipping-tracking/shipments/{created_shipment['id']}/", headers=auth_headers)
        assert response.status_code == 200

    async def test_get_by_id_not_found(self, async_client: AsyncClient, auth_headers):
        """GET /v1/shipping-tracking/shipments/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/shipping-tracking/shipments/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 404

    async def test_admin_can_get_any_shipment(self, async_client: AsyncClient, admin_headers, created_shipment):
        """GET /v1/shipping-tracking/shipments/{id} - Admin can view any shipment."""
        response = await async_client.get(f"/v1/shipping-tracking/shipments/{created_shipment['id']}/", headers=admin_headers)
        assert response.status_code == 200

    async def test_cannot_get_another_users_shipment(self, async_client: AsyncClient, created_shipment):
        """GET /v1/shipping-tracking/shipments/{id} - A different, non-admin user can't view it."""
        email = f"other_{uuid4().hex[:8]}@example.com"
        register_resp = await async_client.post("/v1/auth/register/", json={
            "email": email, "password": "SecurePass123!", "first_name": "Other", "last_name": "User",
        })
        assert register_resp.status_code in (200, 201)
        login_resp = await async_client.post("/v1/auth/login/", json={"email": email, "password": "SecurePass123!"})
        other_headers = {"Authorization": f"Bearer {login_resp.json()['data']['access_token']}"}

        response = await async_client.get(
            f"/v1/shipping-tracking/shipments/{created_shipment['id']}/", headers=other_headers
        )
        assert response.status_code == 404

    async def test_list_own(self, async_client: AsyncClient, auth_headers, created_shipment):
        """GET /v1/shipping-tracking/shipments - List own shipments."""
        response = await async_client.get("/v1/shipping-tracking/shipments/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["pagination"]["total"] >= 1

    async def test_update_status(self, async_client: AsyncClient, admin_headers, created_shipment):
        """PATCH /v1/shipping-tracking/shipments/{id}/status - Admin updates tracking status."""
        response = await async_client.patch(f"/v1/shipping-tracking/shipments/{created_shipment['id']}/status/",
            headers=admin_headers, json={"status": "in_transit", "event_description": "Left warehouse"}
        )
        assert response.status_code == 200

    async def test_customer_cannot_update_status(self, async_client: AsyncClient, auth_headers, created_shipment):
        """A customer must not be able to mark their (or anyone's) shipment delivered."""
        response = await async_client.patch(f"/v1/shipping-tracking/shipments/{created_shipment['id']}/status/",
            headers=auth_headers, json={"status": "delivered"})
        assert response.status_code == 403

    async def test_customer_cannot_create_shipments(self, async_client: AsyncClient, auth_headers, created_provider, own_order):
        response = await async_client.post("/v1/shipping-tracking/shipments/", headers=auth_headers, json={
            "order_id": str(own_order.id), "carrier": created_provider["carrier"], "tracking_number": "TRACKX"})
        assert response.status_code == 403

    async def test_order_shipments_for_owner_and_staff(self, async_client: AsyncClient, auth_headers, admin_headers, created_shipment):
        url = f"/v1/orders/{created_shipment['order_id']}/shipments/"
        own = await async_client.get(url, headers=auth_headers)
        assert [s["id"] for s in own.json()["data"]] == [created_shipment["id"]]
        staff = await async_client.get(url, headers=admin_headers)
        assert [s["id"] for s in staff.json()["data"]] == [created_shipment["id"]]
        unknown = await async_client.get(f"/v1/orders/{uuid4()}/shipments/", headers=auth_headers)
        assert unknown.status_code == 404

    async def test_admin_lists_all_shipments(self, async_client: AsyncClient, admin_headers, created_shipment):
        response = await async_client.get("/v1/shipping-tracking/shipments/?limit=100", headers=admin_headers)
        assert created_shipment["id"] in [s["id"] for s in response.json()["data"]]

    async def test_track(self, async_client: AsyncClient, auth_headers, created_shipment):
        """POST /v1/shipping-tracking/track - Track a shipment via carrier integration."""
        response = await async_client.post("/v1/shipping-tracking/track/", headers=auth_headers, json={
            "tracking_number": created_shipment["tracking_number"], "carrier": created_shipment["carrier"]
        })
        assert response.status_code in [200, 400]
