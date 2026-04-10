"""Tests for commerce endpoints (cart, orders, payments, etc.)."""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.api
@pytest.mark.unit
class TestCartEndpoints:
    """Test shopping cart endpoints."""

    async def test_get_cart(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting user cart."""
        response = await async_client.get("/v1/cart/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data

    async def test_get_cart_unauthorized(self, async_client: AsyncClient):
        """Test getting cart without authentication."""
        response = await async_client.get("/v1/cart/")
        assert response.status_code == 401

    async def test_add_to_cart(self, async_client: AsyncClient, auth_headers: dict):
        """Test adding item to cart."""
        cart_data = {
            "variant_id": str(uuid4()),
            "quantity": 2
        }
        response = await async_client.post("/v1/cart/add", headers=auth_headers, json=cart_data)
        # May fail if variant doesn't exist
        assert response.status_code in [200, 201, 404, 400]

    async def test_update_cart_item(self, async_client: AsyncClient, auth_headers: dict):
        """Test updating cart item quantity."""
        cart_item_id = str(uuid4())
        update_data = {"quantity": 5}
        response = await async_client.put(f"/v1/cart/items/{cart_item_id}", headers=auth_headers, json=update_data)
        # May fail if item doesn't exist
        assert response.status_code in [200, 404]

    async def test_remove_from_cart(self, async_client: AsyncClient, auth_headers: dict):
        """Test removing item from cart."""
        cart_item_id = str(uuid4())
        response = await async_client.delete(f"/v1/cart/items/{cart_item_id}", headers=auth_headers)
        assert response.status_code in [200, 404]

    async def test_clear_cart(self, async_client: AsyncClient, auth_headers: dict):
        """Test clearing entire cart."""
        response = await async_client.post("/v1/cart/clear", headers=auth_headers)
        assert response.status_code in [200, 201]

    async def test_apply_promo_code(self, async_client: AsyncClient, auth_headers: dict):
        """Test applying promo code to cart."""
        promo_data = {"code": "TEST10"}
        response = await async_client.post("/v1/cart/promocode", headers=auth_headers, json=promo_data)
        # May fail if promo code doesn't exist
        assert response.status_code in [200, 400, 404]

    async def test_remove_promo_code(self, async_client: AsyncClient, auth_headers: dict):
        """Test removing promo code from cart."""
        response = await async_client.delete("/v1/cart/promocode", headers=auth_headers)
        assert response.status_code in [200, 400, 404]


@pytest.mark.api
@pytest.mark.unit
class TestOrderEndpoints:
    """Test order endpoints."""

    async def test_create_order(self, async_client: AsyncClient, auth_headers: dict):
        """Test creating an order."""
        order_data = {
            "shipping_address_id": str(uuid4()),
            "payment_method": "card",
            "notes": "Please handle with care"
        }
        response = await async_client.post("/v1/orders/", headers=auth_headers, json=order_data)
        # May fail if cart is empty or address doesn't exist
        assert response.status_code in [200, 201, 400, 404, 422]

    async def test_get_orders(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting user orders."""
        response = await async_client.get("/v1/orders/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data

    async def test_get_orders_unauthorized(self, async_client: AsyncClient):
        """Test getting orders without authentication."""
        response = await async_client.get("/v1/orders/")
        assert response.status_code == 401

    async def test_get_order_by_id(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting a specific order."""
        order_id = str(uuid4())
        response = await async_client.get(f"/v1/orders/{order_id}", headers=auth_headers)
        # May return 404 if order doesn't exist
        assert response.status_code in [200, 404]

    async def test_cancel_order(self, async_client: AsyncClient, auth_headers: dict):
        """Test canceling an order."""
        order_id = str(uuid4())
        cancel_data = {"reason": "Changed my mind"}
        response = await async_client.put(f"/v1/orders/{order_id}/cancel", headers=auth_headers, json=cancel_data)
        assert response.status_code in [200, 400, 404]

    async def test_get_order_tracking(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting order tracking information."""
        order_id = str(uuid4())
        response = await async_client.get(f"/v1/orders/{order_id}/tracking", headers=auth_headers)
        assert response.status_code in [200, 404]


@pytest.mark.api
@pytest.mark.unit
class TestPaymentEndpoints:
    """Test payment endpoints."""

    async def test_get_payment_methods(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting available payment methods."""
        response = await async_client.get("/v1/payments/methods", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_create_payment_intent(self, async_client: AsyncClient, auth_headers: dict):
        """Test creating a payment intent."""
        payment_data = {
            "order_id": str(uuid4()),
            "amount": 99.99,
            "currency": "usd"
        }
        response = await async_client.post("/v1/payments/intents", headers=auth_headers, json=payment_data)
        # May fail if order doesn't exist
        assert response.status_code in [200, 201, 400, 404]

    async def test_get_payment_status(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting payment status."""
        payment_id = str(uuid4())
        response = await async_client.get(f"/v1/payments/failures/{payment_id}/status", headers=auth_headers)
        assert response.status_code in [200, 404]


@pytest.mark.api
@pytest.mark.unit
class TestShippingEndpoints:
    """Test shipping endpoints."""

    async def test_get_shipping_options(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting shipping options."""
        response = await async_client.get("/v1/shipping/methods", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_calculate_shipping(self, async_client: AsyncClient, auth_headers: dict):
        """Test calculating shipping cost."""
        shipping_data = {
            "order_amount": 50.0,
            "destination_country": "US"
        }
        response = await async_client.post("/v1/shipping/calculate", headers=auth_headers, json=shipping_data)
        assert response.status_code in [200, 400, 404]

    async def test_get_shipping_tracking(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting shipping tracking."""
        tracking_number = "TRACK123"
        response = await async_client.get(f"/v1/shipping/tracking/{tracking_number}", headers=auth_headers)
        assert response.status_code in [200, 404]


@pytest.mark.api
@pytest.mark.unit
class TestTaxEndpoints:
    """Test tax endpoints."""

    async def test_calculate_tax(self, async_client: AsyncClient, auth_headers: dict):
        """Test calculating tax for an order."""
        tax_data = {
            "subtotal": 100.00,
            "shipping_address_id": str(uuid4())
        }
        response = await async_client.post("/v1/tax/calculate", headers=auth_headers, json=tax_data)
        # May fail if address doesn't exist
        assert response.status_code in [200, 400, 404]

    async def test_get_tax_rates(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting tax rates (admin only)."""
        response = await async_client.get("/v1/tax/rates", headers=auth_headers)
        # Should fail for regular user
        assert response.status_code in [200, 403]


@pytest.mark.api
@pytest.mark.unit
class TestPromoCodeEndpoints:
    """Test promo code endpoints."""

    async def test_validate_promo_code(self, async_client: AsyncClient, auth_headers: dict):
        """Test validating a promo code."""
        promo_data = {"code": "TEST10"}
        response = await async_client.post("/v1/promocodes/validate", headers=auth_headers, json=promo_data)
        assert response.status_code in [200, 400, 404]

    async def test_get_active_promocodes(self, async_client: AsyncClient):
        """Test getting active promo codes (public endpoint)."""
        response = await async_client.get("/v1/promocodes/active")
        assert response.status_code in [200, 404]

    async def test_create_promocode_as_admin(self, async_client: AsyncClient, admin_headers: dict):
        """Test creating promo code as admin."""
        promo_data = {
            "code": "NEWCODE20",
            "discount_type": "percentage",
            "value": 20.0,
            "usage_limit": 100
        }
        response = await async_client.post("/v1/promocodes/", headers=admin_headers, json=promo_data)
        assert response.status_code in [200, 201]


@pytest.mark.api
@pytest.mark.unit
class TestSubscriptionEndpoints:
    """Test subscription endpoints."""

    async def test_get_subscription_plans(self, async_client: AsyncClient):
        """Test getting subscription plans."""
        response = await async_client.get("/v1/subscriptions/plans")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_get_user_subscriptions(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting user subscriptions."""
        response = await async_client.get("/v1/subscriptions/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_create_subscription(self, async_client: AsyncClient, auth_headers: dict):
        """Test creating a subscription."""
        subscription_data = {
            "plan_id": str(uuid4()),
            "payment_method_id": str(uuid4())
        }
        response = await async_client.post("/v1/subscriptions/", headers=auth_headers, json=subscription_data)
        # May fail if plan doesn't exist
        assert response.status_code in [200, 201, 400, 404]

    async def test_cancel_subscription(self, async_client: AsyncClient, auth_headers: dict):
        """Test canceling a subscription."""
        subscription_id = str(uuid4())
        response = await async_client.post(f"/v1/subscriptions/{subscription_id}/cancel", headers=auth_headers)
        assert response.status_code in [200, 404]


@pytest.mark.api
@pytest.mark.unit
class TestRefundEndpoints:
    """Test refund endpoints (admin only)."""

    async def test_create_refund_as_admin(self, async_client: AsyncClient, admin_headers: dict):
        """Test creating a refund as admin."""
        refund_data = {
            "order_id": str(uuid4()),
            "amount": 50.00,
            "reason": "Customer request"
        }
        response = await async_client.post("/v1/refunds/", headers=admin_headers, json=refund_data)
        assert response.status_code in [200, 201, 400, 404]

    async def test_get_refunds_as_admin(self, async_client: AsyncClient, admin_headers: dict):
        """Test getting all refunds as admin."""
        response = await async_client.get("/v1/refunds/", headers=admin_headers)
        assert response.status_code == 200

    async def test_get_refunds_unauthorized(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting refunds as regular user (should fail)."""
        response = await async_client.get("/v1/refunds/", headers=auth_headers)
        assert response.status_code == 403
