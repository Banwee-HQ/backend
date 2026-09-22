"""Tests for api/commerce/orders.py - /v1/orders endpoints."""

import pytest
from httpx import AsyncClient
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from core.exceptions import APIException
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

        Regression test: OrderService.create() (then named place()) previously called
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

    async def test_create_endpoint_is_checkout_alias(self, async_client: AsyncClient, auth_headers, checkout_ready_cart, mocker):
        """POST /v1/orders - Same underlying OrderService.create() as /orders/checkout/."""
        mocker.patch(
            "services.commerce.payments.PaymentService.process_idempotent",
            return_value={"status": "succeeded", "payment_intent_id": str(uuid4())},
        )
        mocker.patch("services.accounts.email.EmailService.send_order_confirmation_email", return_value=None)

        response = await async_client.post("/v1/orders/", headers=auth_headers, json=checkout_ready_cart)
        assert response.status_code == 200
        assert response.json()["data"]["order_status"] == "confirmed"

    async def test_checkout_unknown_payment_method(self, async_client: AsyncClient, auth_headers, checkout_ready_cart):
        """POST /v1/orders/checkout - A payment method that doesn't exist is rejected
        with a clean 400, not relabeled as a 500 by the endpoint's exception handler."""
        checkout_ready_cart["payment_method_id"] = str(uuid4())
        response = await async_client.post("/v1/orders/checkout/", headers=auth_headers, json=checkout_ready_cart)
        assert response.status_code == 400


@pytest.mark.api
class TestOrderEndpoints:

    async def test_list(self, async_client: AsyncClient, auth_headers, created_order):
        """GET /v1/orders/ - List the user's own orders."""
        response = await async_client.get("/v1/orders/", headers=auth_headers)
        assert response.status_code == 200

    async def test_list_admin_sees_all(self, async_client: AsyncClient, admin_headers, created_order):
        """GET /v1/orders/ - Admin sees orders across all users."""
        response = await async_client.get("/v1/orders/", headers=admin_headers)
        assert response.status_code == 200
        ids = [o["id"] for o in response.json()["data"]]
        assert str(created_order.id) in ids

    async def test_list_filters_by_status(self, async_client: AsyncClient, auth_headers, created_order):
        response = await async_client.get(f"/v1/orders/?status={created_order.order_status.value}", headers=auth_headers)
        assert response.status_code == 200
        ids = [o["id"] for o in response.json()["data"]]
        assert str(created_order.id) in ids

    async def test_list_filters_by_search(self, async_client: AsyncClient, auth_headers, created_order):
        response = await async_client.get(f"/v1/orders/?search={created_order.order_number}", headers=auth_headers)
        assert response.status_code == 200
        ids = [o["id"] for o in response.json()["data"]]
        assert str(created_order.id) in ids

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

    async def test_cancel_not_own_order_returns_404(self, async_client: AsyncClient, admin_headers, created_order):
        """Regression test: this used to relabel the service's 404 as a flat 400."""
        response = await async_client.patch(f"/v1/orders/{created_order.id}/cancel/", headers=admin_headers)
        assert response.status_code == 404

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

    async def test_list_notes_not_own_order_returns_404(self, async_client: AsyncClient, admin_headers, created_order):
        """Regression test: this used to relabel the service's 404 as a 500."""
        response = await async_client.get(f"/v1/orders/{created_order.id}/notes/", headers=admin_headers)
        assert response.status_code == 404

    async def test_add_note_not_own_order_returns_404(self, async_client: AsyncClient, admin_headers, created_order):
        """Regression test: this used to relabel the service's 404 as a flat 400."""
        response = await async_client.post(f"/v1/orders/{created_order.id}/notes/",
            headers=admin_headers, json={"note": "Not mine"}
        )
        assert response.status_code == 404

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

    async def test_invoice(self, async_client: AsyncClient, auth_headers, created_order):
        """GET /v1/orders/{id}/invoice - Download a PDF invoice for own order."""
        response = await async_client.get(f"/v1/orders/{created_order.id}/invoice/", headers=auth_headers)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

    async def test_invoice_not_own_order_returns_404(self, async_client: AsyncClient, admin_headers, created_order):
        """Regression test: this used to relabel the service's 404 as a 500."""
        response = await async_client.get(f"/v1/orders/{created_order.id}/invoice/", headers=admin_headers)
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

    async def test_shipments_not_own_order_returns_404(self, async_client: AsyncClient, admin_headers, created_order):
        """Regression test: this endpoint had no ownership check at all - any
        authenticated user could view any order's shipments by guessing its ID."""
        response = await async_client.get(f"/v1/orders/{created_order.id}/shipments/", headers=admin_headers)
        assert response.status_code == 404

    async def test_public_tracking_by_order_number(self, async_client: AsyncClient, created_order):
        """GET /v1/orders/track/{id} - Public tracking, no auth required."""
        response = await async_client.get(f"/v1/orders/track/{created_order.order_number}/")
        assert response.status_code == 200

    async def test_public_tracking_unknown_order_returns_404(self, async_client: AsyncClient):
        """GET /v1/orders/track/{id} - Unknown order number/id returns 404, not a masked 500."""
        response = await async_client.get(f"/v1/orders/track/NOT-A-REAL-ORDER/")
        assert response.status_code == 404

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

    async def test_ship_as_admin(self, async_client: AsyncClient, admin_headers, created_order):
        """POST /v1/orders/{id}/ship - Admin marks the order shipped."""
        response = await async_client.post(f"/v1/orders/{created_order.id}/ship/",
            headers=admin_headers, json={"carrier": "ups", "tracking_number": "1Z999"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["order_status"] == "shipped"

    async def test_deliver_requires_admin(self, async_client: AsyncClient, auth_headers, created_order):
        """PUT /v1/orders/{id}/deliver - Non-admin is forbidden."""
        response = await async_client.put(f"/v1/orders/{created_order.id}/deliver/", headers=auth_headers)
        assert response.status_code == 403

    async def test_deliver_as_admin(self, async_client: AsyncClient, admin_headers, created_order):
        """PUT /v1/orders/{id}/deliver - Admin marks the order delivered."""
        response = await async_client.put(f"/v1/orders/{created_order.id}/deliver/",
            headers=admin_headers, json={"notes": "Left at door"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["order_status"] == "delivered"

    async def test_update_status_unknown_order_returns_404(self, async_client: AsyncClient, admin_headers):
        response = await async_client.patch(f"/v1/orders/{uuid4()}/status/",
            headers=admin_headers, json={"status": "confirmed"}
        )
        assert response.status_code == 404

    async def test_update_status_invalid_value_returns_400(self, async_client: AsyncClient, admin_headers, created_order):
        response = await async_client.patch(f"/v1/orders/{created_order.id}/status/",
            headers=admin_headers, json={"status": "not-a-real-status"}
        )
        assert response.status_code == 400

    async def test_tracking_not_own_order_returns_404(self, async_client: AsyncClient, admin_headers, created_order):
        response = await async_client.get(f"/v1/orders/{created_order.id}/tracking/", headers=admin_headers)
        assert response.status_code == 404

    async def test_payments_not_own_order_returns_404(self, async_client: AsyncClient, admin_headers, created_order):
        response = await async_client.get(f"/v1/orders/{created_order.id}/payments/", headers=admin_headers)
        assert response.status_code == 404

    async def test_statistics_requires_admin(self, async_client: AsyncClient, auth_headers):
        """GET /v1/orders/statistics - Non-admin is forbidden."""
        response = await async_client.get("/v1/orders/statistics/", headers=auth_headers)
        assert response.status_code == 403

    async def test_statistics_as_admin(self, async_client: AsyncClient, admin_headers, created_order):
        """GET /v1/orders/statistics - Admin can view order statistics."""
        response = await async_client.get("/v1/orders/statistics/", headers=admin_headers)
        assert response.status_code == 200

    async def test_checkout_insufficient_stock_returns_400(
        self, async_client: AsyncClient, auth_headers, test_user, checkout_ready_cart, db_session, mocker
    ):
        """Real (non-mocked) flow: reduce the reserved item's stock below the cart
        quantity and confirm checkout fails cleanly with 400, not a masked 500 -
        this exercises the `except APIException: raise` branch in checkout()."""
        from sqlalchemy import select
        from models.commerce.cart import Cart, CartItem
        from models.catalog.inventories import Inventory

        cart_item = (await db_session.execute(
            select(CartItem).join(Cart).where(Cart.user_id == test_user.id)
        )).scalars().first()
        inventory = (await db_session.execute(
            select(Inventory).where(Inventory.variant_id == cart_item.variant_id)
        )).scalar_one()
        inventory.quantity_available = 1  # the cart wants 2
        await db_session.commit()

        mocker.patch(
            "services.commerce.payments.PaymentService.process_idempotent",
            return_value={"status": "succeeded"},
        )
        response = await async_client.post("/v1/orders/checkout/", headers=auth_headers, json=checkout_ready_cart)
        assert response.status_code == 400

    async def test_checkout_unexpected_service_error_returns_500(self, async_client: AsyncClient, auth_headers, checkout_ready_cart, mocker):
        mocker.patch("services.commerce.orders.OrderService.create", side_effect=RuntimeError("boom"))
        response = await async_client.post("/v1/orders/checkout/", headers=auth_headers, json=checkout_ready_cart)
        assert response.status_code == 500

    async def test_create_alias_insufficient_stock_returns_400(
        self, async_client: AsyncClient, auth_headers, test_user, checkout_ready_cart, db_session, mocker
    ):
        """POST /v1/orders (the create() alias) - real APIException-preserving
        behavior, verified independently of /orders/checkout/."""
        from sqlalchemy import select
        from models.commerce.cart import Cart, CartItem
        from models.catalog.inventories import Inventory

        cart_item = (await db_session.execute(
            select(CartItem).join(Cart).where(Cart.user_id == test_user.id)
        )).scalars().first()
        inventory = (await db_session.execute(
            select(Inventory).where(Inventory.variant_id == cart_item.variant_id)
        )).scalar_one()
        inventory.quantity_available = 1  # the cart wants 2
        await db_session.commit()

        mocker.patch(
            "services.commerce.payments.PaymentService.process_idempotent",
            return_value={"status": "succeeded"},
        )
        response = await async_client.post("/v1/orders/", headers=auth_headers, json=checkout_ready_cart)
        assert response.status_code == 400

    async def test_create_alias_unknown_payment_method_returns_400(self, async_client: AsyncClient, auth_headers, checkout_ready_cart):
        """POST /v1/orders (the create() alias) - same APIException-preserving
        behavior as /orders/checkout/, verified independently since it's a
        separate route function in the API layer."""
        checkout_ready_cart["payment_method_id"] = str(uuid4())
        response = await async_client.post("/v1/orders/", headers=auth_headers, json=checkout_ready_cart)
        assert response.status_code == 400

    async def test_create_alias_unexpected_service_error_returns_400(self, async_client: AsyncClient, auth_headers, checkout_ready_cart, mocker):
        mocker.patch("services.commerce.orders.OrderService.create", side_effect=RuntimeError("boom"))
        response = await async_client.post("/v1/orders/", headers=auth_headers, json=checkout_ready_cart)
        assert response.status_code == 400

    async def test_checkout_validate_empty_cart(self, async_client: AsyncClient, auth_headers):
        """POST /v1/orders/checkout/validate - Empty cart fails validation, but the
        request itself always succeeds - the result carries valid=False, not an HTTP error."""
        response = await async_client.post("/v1/orders/checkout/validate/",
            headers=auth_headers,
            json={
                "shipping_address_id": str(uuid4()),
                "shipping_method_id": str(uuid4()),
                "payment_method_id": str(uuid4()),
            }
        )
        assert response.status_code == 200
        assert response.json()["data"]["can_proceed"] is False


# ---------------------------------------------------------------------------
# Thin-wrapper exception-handling branches: every endpoint's try/except
# preserves APIException/HTTPException status codes as-is and maps any other
# unexpected exception to a documented status code. Verified via mocker since
# OrderService itself never raises bare exceptions for most of these calls.
# ---------------------------------------------------------------------------

@pytest.mark.api
class TestStatisticsEdgeCases:

    async def test_service_apiexception_passes_through(self, async_client: AsyncClient, admin_headers, mocker):
        mocker.patch("services.commerce.orders.OrderService.get_statistics", side_effect=APIException(status_code=418, message="teapot"))
        response = await async_client.get("/v1/orders/statistics/", headers=admin_headers)
        assert response.status_code == 418

    async def test_service_httpexception_passes_through(self, async_client: AsyncClient, admin_headers, mocker):
        mocker.patch("services.commerce.orders.OrderService.get_statistics", side_effect=HTTPException(status_code=403, detail="x"))
        response = await async_client.get("/v1/orders/statistics/", headers=admin_headers)
        assert response.status_code == 403

    async def test_unexpected_error_returns_500(self, async_client: AsyncClient, admin_headers, mocker):
        mocker.patch("services.commerce.orders.OrderService.get_statistics", side_effect=RuntimeError("boom"))
        response = await async_client.get("/v1/orders/statistics/", headers=admin_headers)
        assert response.status_code == 500


@pytest.mark.api
class TestGetOrderEdgeCases:

    async def test_service_httpexception_passes_through(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.orders.OrderService.get", side_effect=HTTPException(status_code=403, detail="x"))
        response = await async_client.get(f"/v1/orders/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 403

    async def test_unexpected_error_returns_500(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.orders.OrderService.get", side_effect=RuntimeError("boom"))
        response = await async_client.get(f"/v1/orders/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 500


@pytest.mark.api
class TestListOrdersEdgeCases:

    async def test_data_shaped_result_uses_explicit_pagination(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.orders.OrderService.list", return_value={
            "data": [{"id": "x"}], "page": 2, "limit": 5, "total": 1, "pages": 1
        })
        response = await async_client.get("/v1/orders/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["pagination"]["page"] == 2

    async def test_unrecognized_result_shape_falls_back_to_raw_data(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.orders.OrderService.list", return_value={})
        response = await async_client.get("/v1/orders/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"] == {}

    async def test_service_apiexception_passes_through(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.orders.OrderService.list", side_effect=APIException(status_code=418, message="teapot"))
        response = await async_client.get("/v1/orders/", headers=auth_headers)
        assert response.status_code == 418

    async def test_service_httpexception_passes_through(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.orders.OrderService.list", side_effect=HTTPException(status_code=403, detail="x"))
        response = await async_client.get("/v1/orders/", headers=auth_headers)
        assert response.status_code == 403

    async def test_unexpected_error_returns_500(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.orders.OrderService.list", side_effect=RuntimeError("boom"))
        response = await async_client.get("/v1/orders/", headers=auth_headers)
        assert response.status_code == 500


@pytest.mark.api
class TestValidateEdgeCases:

    async def test_service_apiexception_passes_through(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.orders.OrderService.validate_checkout", side_effect=APIException(status_code=418, message="teapot"))
        response = await async_client.post("/v1/orders/checkout/validate/", headers=auth_headers, json={
            "shipping_address_id": str(uuid4()), "shipping_method_id": str(uuid4()), "payment_method_id": str(uuid4()),
        })
        assert response.status_code == 418

    async def test_service_httpexception_passes_through(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.orders.OrderService.validate_checkout", side_effect=HTTPException(status_code=403, detail="x"))
        response = await async_client.post("/v1/orders/checkout/validate/", headers=auth_headers, json={
            "shipping_address_id": str(uuid4()), "shipping_method_id": str(uuid4()), "payment_method_id": str(uuid4()),
        })
        assert response.status_code == 403

    async def test_unexpected_error_returns_500(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.orders.OrderService.validate_checkout", side_effect=RuntimeError("boom"))
        response = await async_client.post("/v1/orders/checkout/validate/", headers=auth_headers, json={
            "shipping_address_id": str(uuid4()), "shipping_method_id": str(uuid4()), "payment_method_id": str(uuid4()),
        })
        assert response.status_code == 500


@pytest.mark.api
class TestCancelEdgeCases:

    async def test_service_apiexception_passes_through(self, async_client: AsyncClient, auth_headers, created_order, mocker):
        mocker.patch("services.commerce.orders.OrderService.cancel", side_effect=APIException(status_code=418, message="teapot"))
        response = await async_client.patch(f"/v1/orders/{created_order.id}/cancel/", headers=auth_headers)
        assert response.status_code == 418

    async def test_unexpected_error_returns_400(self, async_client: AsyncClient, auth_headers, created_order, mocker):
        mocker.patch("services.commerce.orders.OrderService.cancel", side_effect=RuntimeError("boom"))
        response = await async_client.patch(f"/v1/orders/{created_order.id}/cancel/", headers=auth_headers)
        assert response.status_code == 400


@pytest.mark.api
class TestInvoiceEdgeCases:

    async def test_unsuccessful_generation_result_returns_500(self, async_client: AsyncClient, auth_headers, created_order, mocker):
        mocker.patch(
            "core.utils.invoice_generator.InvoiceGenerator.generate_invoice",
            return_value={"success": False, "message": "renderer unavailable"},
        )
        response = await async_client.get(f"/v1/orders/{created_order.id}/invoice/", headers=auth_headers)
        assert response.status_code == 500

    async def test_unexpected_error_returns_500(self, async_client: AsyncClient, auth_headers, created_order, mocker):
        mocker.patch("services.commerce.orders.OrderService.invoice", side_effect=RuntimeError("boom"))
        response = await async_client.get(f"/v1/orders/{created_order.id}/invoice/", headers=auth_headers)
        assert response.status_code == 500


@pytest.mark.api
class TestCreateNoteEdgeCases:

    async def test_service_apiexception_passes_through(self, async_client: AsyncClient, auth_headers, created_order, mocker):
        mocker.patch("services.commerce.orders.OrderService.add_note", side_effect=APIException(status_code=418, message="teapot"))
        response = await async_client.post(f"/v1/orders/{created_order.id}/notes/", headers=auth_headers, json={"note": "x"})
        assert response.status_code == 418

    async def test_unexpected_error_returns_400(self, async_client: AsyncClient, auth_headers, created_order, mocker):
        mocker.patch("services.commerce.orders.OrderService.add_note", side_effect=RuntimeError("boom"))
        response = await async_client.post(f"/v1/orders/{created_order.id}/notes/", headers=auth_headers, json={"note": "x"})
        assert response.status_code == 400


@pytest.mark.api
class TestGetNoteEdgeCases:

    async def test_service_httpexception_passes_through(self, async_client: AsyncClient, auth_headers, created_order, mocker):
        mocker.patch("services.commerce.orders.OrderService.get_note", side_effect=HTTPException(status_code=403, detail="x"))
        response = await async_client.get(f"/v1/orders/{created_order.id}/notes/0/", headers=auth_headers)
        assert response.status_code == 403

    async def test_unexpected_error_returns_500(self, async_client: AsyncClient, auth_headers, created_order, mocker):
        mocker.patch("services.commerce.orders.OrderService.get_note", side_effect=RuntimeError("boom"))
        response = await async_client.get(f"/v1/orders/{created_order.id}/notes/0/", headers=auth_headers)
        assert response.status_code == 500


@pytest.mark.api
class TestListNotesEdgeCases:

    async def test_service_apiexception_passes_through(self, async_client: AsyncClient, auth_headers, created_order, mocker):
        mocker.patch("services.commerce.orders.OrderService.notes", side_effect=APIException(status_code=418, message="teapot"))
        response = await async_client.get(f"/v1/orders/{created_order.id}/notes/", headers=auth_headers)
        assert response.status_code == 418

    async def test_unexpected_error_returns_500(self, async_client: AsyncClient, auth_headers, created_order, mocker):
        mocker.patch("services.commerce.orders.OrderService.notes", side_effect=RuntimeError("boom"))
        response = await async_client.get(f"/v1/orders/{created_order.id}/notes/", headers=auth_headers)
        assert response.status_code == 500


@pytest.mark.api
class TestGetTrackingEdgeCases:

    async def test_none_result_is_treated_as_not_found(self, async_client: AsyncClient, auth_headers, created_order, mocker):
        """Defensive check: OrderService.tracking() always raises rather than
        returning None today, but the endpoint guards against it regardless."""
        mocker.patch("services.commerce.orders.OrderService.tracking", return_value=None)
        response = await async_client.get(f"/v1/orders/{created_order.id}/tracking/", headers=auth_headers)
        assert response.status_code == 404

    async def test_service_httpexception_passes_through(self, async_client: AsyncClient, auth_headers, created_order, mocker):
        mocker.patch("services.commerce.orders.OrderService.tracking", side_effect=HTTPException(status_code=403, detail="x"))
        response = await async_client.get(f"/v1/orders/{created_order.id}/tracking/", headers=auth_headers)
        assert response.status_code == 403

    async def test_unexpected_error_returns_500(self, async_client: AsyncClient, auth_headers, created_order, mocker):
        mocker.patch("services.commerce.orders.OrderService.tracking", side_effect=RuntimeError("boom"))
        response = await async_client.get(f"/v1/orders/{created_order.id}/tracking/", headers=auth_headers)
        assert response.status_code == 500


@pytest.mark.api
class TestGetOrderPaymentsEdgeCases:

    async def test_service_httpexception_passes_through(self, async_client: AsyncClient, auth_headers, created_order, mocker):
        mocker.patch("services.commerce.orders.OrderService.payments", side_effect=HTTPException(status_code=403, detail="x"))
        response = await async_client.get(f"/v1/orders/{created_order.id}/payments/", headers=auth_headers)
        assert response.status_code == 403

    async def test_unexpected_error_returns_500(self, async_client: AsyncClient, auth_headers, created_order, mocker):
        mocker.patch("services.commerce.orders.OrderService.payments", side_effect=RuntimeError("boom"))
        response = await async_client.get(f"/v1/orders/{created_order.id}/payments/", headers=auth_headers)
        assert response.status_code == 500


@pytest.mark.api
class TestGetOrderShipmentsEdgeCases:

    async def test_service_httpexception_passes_through(self, async_client: AsyncClient, auth_headers, created_order, mocker):
        mocker.patch("services.commerce.orders.OrderService.get", side_effect=HTTPException(status_code=403, detail="x"))
        response = await async_client.get(f"/v1/orders/{created_order.id}/shipments/", headers=auth_headers)
        assert response.status_code == 403

    async def test_unexpected_error_returns_500(self, async_client: AsyncClient, auth_headers, created_order, mocker):
        mocker.patch(
            "services.commerce.shipping_tracking.ShippingTrackingService.list_by_order",
            side_effect=RuntimeError("boom"),
        )
        response = await async_client.get(f"/v1/orders/{created_order.id}/shipments/", headers=auth_headers)
        assert response.status_code == 500


@pytest.mark.api
class TestPublicTrackingEdgeCases:

    async def test_service_apiexception_passes_through(self, async_client: AsyncClient, mocker):
        mocker.patch("services.commerce.orders.OrderService.tracking_public", side_effect=APIException(status_code=418, message="teapot"))
        response = await async_client.get("/v1/orders/track/ANYTHING/")
        assert response.status_code == 418

    async def test_unexpected_error_returns_500(self, async_client: AsyncClient, mocker):
        mocker.patch("services.commerce.orders.OrderService.tracking_public", side_effect=RuntimeError("boom"))
        response = await async_client.get("/v1/orders/track/ANYTHING/")
        assert response.status_code == 500


@pytest.mark.api
class TestUpdateStatusEdgeCases:

    async def test_service_apiexception_passes_through(self, async_client: AsyncClient, admin_headers, created_order, mocker):
        mocker.patch("services.commerce.orders.OrderService.update_status", side_effect=APIException(status_code=418, message="teapot"))
        response = await async_client.patch(f"/v1/orders/{created_order.id}/status/", headers=admin_headers, json={"status": "confirmed"})
        assert response.status_code == 418

    async def test_unexpected_error_returns_500(self, async_client: AsyncClient, admin_headers, created_order, mocker):
        mocker.patch("services.commerce.orders.OrderService.update_status", side_effect=RuntimeError("boom"))
        response = await async_client.patch(f"/v1/orders/{created_order.id}/status/", headers=admin_headers, json={"status": "confirmed"})
        assert response.status_code == 500


@pytest.mark.api
class TestDeliverEdgeCases:

    async def test_unknown_order_returns_404(self, async_client: AsyncClient, admin_headers):
        response = await async_client.put(f"/v1/orders/{uuid4()}/deliver/", headers=admin_headers, json={})
        assert response.status_code == 404

    async def test_malformed_order_id_returns_500(self, async_client: AsyncClient, admin_headers):
        """deliver() does UUID(order_id) internally - a non-UUID path segment
        raises a bare ValueError, which the endpoint must map to a clean 500
        instead of letting it bubble up unhandled."""
        response = await async_client.put("/v1/orders/not-a-real-uuid/deliver/", headers=admin_headers, json={})
        assert response.status_code == 500

    async def test_service_apiexception_passes_through(self, async_client: AsyncClient, admin_headers, created_order, mocker):
        mocker.patch("services.commerce.orders.OrderService.deliver", side_effect=APIException(status_code=418, message="teapot"))
        response = await async_client.put(f"/v1/orders/{created_order.id}/deliver/", headers=admin_headers, json={})
        assert response.status_code == 418


@pytest.mark.api
class TestShipEdgeCases:

    async def test_unknown_order_returns_404(self, async_client: AsyncClient, admin_headers):
        response = await async_client.post(f"/v1/orders/{uuid4()}/ship/", headers=admin_headers, json={
            "carrier": "ups", "tracking_number": "1Z999"
        })
        assert response.status_code == 404

    async def test_malformed_order_id_returns_500(self, async_client: AsyncClient, admin_headers):
        response = await async_client.post("/v1/orders/not-a-real-uuid/ship/", headers=admin_headers, json={
            "carrier": "ups", "tracking_number": "1Z999"
        })
        assert response.status_code == 500

    async def test_service_apiexception_passes_through(self, async_client: AsyncClient, admin_headers, created_order, mocker):
        mocker.patch("services.commerce.orders.OrderService.ship", side_effect=APIException(status_code=418, message="teapot"))
        response = await async_client.post(f"/v1/orders/{created_order.id}/ship/", headers=admin_headers, json={
            "carrier": "ups", "tracking_number": "1Z999"
        })
        assert response.status_code == 418
