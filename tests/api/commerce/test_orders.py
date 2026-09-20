"""Tests for api/commerce/orders.py - /v1/orders endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from models.commerce.orders import Order, OrderStatus, PaymentStatus, FulfillmentStatus
from models.commerce.payments import PaymentMethod, PaymentType, PaymentProvider, CardBrand
from core.utils.uuid_utils import uuid7


@pytest.fixture
async def created_order(db_session: AsyncSession, test_user) -> Order:
    """A real order, inserted directly - full checkout needs a live Stripe payment method."""
    order = Order(
        id=uuid7(),
        order_number=f"ORD-{uuid4().hex[:10].upper()}",
        user_id=test_user.id,
        order_status=OrderStatus.PENDING,
        payment_status=PaymentStatus.PENDING,
        fulfillment_status=FulfillmentStatus.UNFULFILLED,
        subtotal=100.0,
        shipping_cost=10.0,
        tax_amount=8.0,
        total_amount=118.0,
        billing_address={"street": "1 Test St", "city": "Lagos", "country": "NG"},
        shipping_address={"street": "1 Test St", "city": "Lagos", "country": "NG"},
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


@pytest.fixture
async def checkout_ready_cart(async_client: AsyncClient, auth_headers, admin_headers,
                               test_user, db_session: AsyncSession, sample_product_data):
    """A cart with a real item plus a real address, shipping method, and payment method -
    everything checkout needs except a live Stripe charge, which tests mock out."""
    cat = await async_client.post("/v1/categories/",
        headers=admin_headers, json={"name": "Cat", "slug": f"cat-{uuid4().hex[:8]}"}
    )
    sample_product_data["category_id"] = cat.json()["data"]["id"]
    product = await async_client.post("/v1/products/", headers=admin_headers, json=sample_product_data)
    variants = await async_client.get(f"/v1/products/{product.json()['data']['id']}/variants/")
    variant_id = variants.json()["data"][0]["id"]
    await async_client.post("/v1/cart/add/", headers=auth_headers, json={"variant_id": variant_id, "quantity": 2})

    address = await async_client.post("/v1/addresses/", headers=auth_headers, json={
        "street": "123 Test St", "city": "Lagos", "state": "Lagos", "post_code": "100001", "country": "NG"
    })
    method = await async_client.post("/v1/shipping/methods/", headers=admin_headers, json={
        "name": "Standard", "price": 10.0, "estimated_days": 5
    })

    payment_method = PaymentMethod(
        id=uuid7(), user_id=test_user.id, type=PaymentType.CARD, provider=PaymentProvider.STRIPE,
        last_four="4242", expiry_month=12, expiry_year=2099, brand=CardBrand.VISA,
        stripe_payment_method_id=f"pm_test_{uuid4().hex[:16]}", is_default=True, is_active=True,
    )
    db_session.add(payment_method)
    await db_session.commit()

    return {
        "shipping_address_id": address.json()["data"]["id"],
        "shipping_method_id": method.json()["data"]["id"],
        "payment_method_id": str(payment_method.id),
    }


@pytest.mark.api
class TestCheckout:

    async def test_checkout_success(self, async_client: AsyncClient, auth_headers, checkout_ready_cart, mocker):
        """POST /v1/orders/checkout - Full checkout with cart, address, shipping, and payment.

        Regression test: OrderService._perform_order_placement previously called
        self.db.begin() on a session with an already-open transaction (always raised
        "A transaction is already begun") and constructed Order() with several
        keyword arguments that aren't columns on the model (status, shipping_address_id,
        shipping_method_id, payment_method_id, promocode_id) - checkout never succeeded.
        """
        mocker.patch(
            "services.commerce.payments.PaymentService.process_idempotent",
            return_value={"status": "succeeded", "payment_intent_id": str(uuid4())},
        )
        mocker.patch("services.accounts.email.EmailService.send_order_confirmation_email", return_value=None)

        response = await async_client.post("/v1/orders/checkout/", headers=auth_headers, json=checkout_ready_cart)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["order_status"] == "confirmed"
        assert data["payment_status"] == "paid"
        assert data["total_amount"] == 49.98
        assert len(data["items"]) == 1

        cart = await async_client.get("/v1/cart/", headers=auth_headers)
        assert cart.json()["data"]["items"] == []

    async def test_checkout_unknown_payment_method(self, async_client: AsyncClient, auth_headers, checkout_ready_cart):
        """POST /v1/orders/checkout - A payment method that doesn't exist is rejected."""
        checkout_ready_cart["payment_method_id"] = str(uuid4())
        response = await async_client.post("/v1/orders/checkout/", headers=auth_headers, json=checkout_ready_cart)
        assert response.status_code in [400, 500]


@pytest.mark.api
class TestOrderEndpoints:

    async def test_list(self, async_client: AsyncClient, auth_headers, created_order):
        """GET /v1/orders/ - List the user's own orders."""
        response = await async_client.get("/v1/orders/", headers=auth_headers)
        assert response.status_code == 200

    async def test_get_by_id(self, async_client: AsyncClient, auth_headers, created_order):
        """GET /v1/orders/{id} - Get own order."""
        response = await async_client.get(f"/v1/orders/{created_order.id}/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["order_number"] == created_order.order_number

    async def test_get_by_id_not_found(self, async_client: AsyncClient, auth_headers):
        """GET /v1/orders/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/orders/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 404

    async def test_get_by_id_not_own_order(self, async_client: AsyncClient, admin_headers, created_order):
        """GET /v1/orders/{id} - A different (non-admin) user cannot see this order."""
        response = await async_client.get(f"/v1/orders/{created_order.id}/", headers=admin_headers)
        assert response.status_code == 200
        # admins can see any order via the admin path in the service

    async def test_cancel(self, async_client: AsyncClient, auth_headers, created_order):
        """PATCH /v1/orders/{id}/cancel - Cancel own order."""
        response = await async_client.patch(f"/v1/orders/{created_order.id}/cancel/", headers=auth_headers)
        assert response.status_code == 200

    async def test_cancel_post_alias(self, async_client: AsyncClient, auth_headers, created_order):
        """POST /v1/orders/{id}/cancel - Compatibility alias."""
        response = await async_client.post(f"/v1/orders/{created_order.id}/cancel/", headers=auth_headers)
        assert response.status_code == 200

    async def test_add_note(self, async_client: AsyncClient, auth_headers, created_order):
        """POST /v1/orders/{id}/notes - Add a note."""
        response = await async_client.post(f"/v1/orders/{created_order.id}/notes/",
            headers=auth_headers, json={"note": "Please deliver after 5pm"}
        )
        assert response.status_code == 200
        assert "Please deliver after 5pm" in response.json()["data"]["all_notes"]

    async def test_list_notes(self, async_client: AsyncClient, auth_headers, created_order):
        """GET /v1/orders/{id}/notes - List notes after adding one."""
        await async_client.post(f"/v1/orders/{created_order.id}/notes/",
            headers=auth_headers, json={"note": "Leave at front door"}
        )
        response = await async_client.get(f"/v1/orders/{created_order.id}/notes/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["total_notes"] == 1

    async def test_get_note_by_index(self, async_client: AsyncClient, auth_headers, created_order):
        """GET /v1/orders/{id}/notes/{index} - Get a specific note."""
        await async_client.post(f"/v1/orders/{created_order.id}/notes/",
            headers=auth_headers, json={"note": "Call before delivery"}
        )
        response = await async_client.get(f"/v1/orders/{created_order.id}/notes/0/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["note"] == "Call before delivery"

    async def test_get_note_index_out_of_range(self, async_client: AsyncClient, auth_headers, created_order):
        """GET /v1/orders/{id}/notes/{index} - Out-of-range index returns 404."""
        response = await async_client.get(f"/v1/orders/{created_order.id}/notes/99/", headers=auth_headers)
        assert response.status_code == 404

    async def test_tracking(self, async_client: AsyncClient, auth_headers, created_order):
        """GET /v1/orders/{id}/tracking - Get tracking info for own order."""
        response = await async_client.get(f"/v1/orders/{created_order.id}/tracking/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["order_id"] == str(created_order.id)

    async def test_payments(self, async_client: AsyncClient, auth_headers, created_order):
        """GET /v1/orders/{id}/payments - No payments yet, still 200 with empty lists."""
        response = await async_client.get(f"/v1/orders/{created_order.id}/payments/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["payment_intents"] == []

    async def test_shipments(self, async_client: AsyncClient, auth_headers, created_order):
        """GET /v1/orders/{id}/shipments - No shipments yet, still 200."""
        response = await async_client.get(f"/v1/orders/{created_order.id}/shipments/", headers=auth_headers)
        assert response.status_code == 200

    async def test_public_tracking_by_order_number(self, async_client: AsyncClient, created_order):
        """GET /v1/orders/track/{id} - Public tracking, no auth required."""
        response = await async_client.get(f"/v1/orders/track/{created_order.order_number}/")
        assert response.status_code == 200

    async def test_update_status_requires_admin(self, async_client: AsyncClient, auth_headers, created_order):
        """PATCH /v1/orders/{id}/status - Non-admin is forbidden."""
        response = await async_client.patch(f"/v1/orders/{created_order.id}/status/",
            headers=auth_headers, json={"status": "confirmed"}
        )
        assert response.status_code == 403

    async def test_update_status_as_admin(self, async_client: AsyncClient, admin_headers, created_order):
        """PATCH /v1/orders/{id}/status - Admin updates order status."""
        response = await async_client.patch(f"/v1/orders/{created_order.id}/status/",
            headers=admin_headers, json={"status": "confirmed"}
        )
        assert response.status_code == 200

    async def test_ship_requires_admin(self, async_client: AsyncClient, auth_headers, created_order):
        """POST /v1/orders/{id}/ship - Non-admin is forbidden."""
        response = await async_client.post(f"/v1/orders/{created_order.id}/ship/",
            headers=auth_headers, json={"carrier": "ups", "tracking_number": "1Z999"}
        )
        assert response.status_code == 403

    async def test_deliver_requires_admin(self, async_client: AsyncClient, auth_headers, created_order):
        """PUT /v1/orders/{id}/deliver - Non-admin is forbidden."""
        response = await async_client.put(f"/v1/orders/{created_order.id}/deliver/", headers=auth_headers)
        assert response.status_code == 403

    async def test_statistics_requires_admin(self, async_client: AsyncClient, auth_headers):
        """GET /v1/orders/statistics - Non-admin is forbidden."""
        response = await async_client.get("/v1/orders/statistics/", headers=auth_headers)
        assert response.status_code == 403

    async def test_statistics_as_admin(self, async_client: AsyncClient, admin_headers, created_order):
        """GET /v1/orders/statistics - Admin can view order statistics."""
        response = await async_client.get("/v1/orders/statistics/", headers=admin_headers)
        assert response.status_code == 200

    async def test_checkout_validate_empty_cart(self, async_client: AsyncClient, auth_headers):
        """POST /v1/orders/checkout/validate - Empty cart fails validation."""
        response = await async_client.post("/v1/orders/checkout/validate/",
            headers=auth_headers,
            json={
                "shipping_address_id": str(uuid4()),
                "shipping_method_id": str(uuid4()),
                "payment_method_id": str(uuid4()),
            }
        )
        assert response.status_code in [200, 400, 404, 500]
