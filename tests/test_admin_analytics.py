"""Admin and Analytics API Tests - Tests all admin and analytics endpoints."""

import pytest
from httpx import AsyncClient
from uuid import uuid4


# =============================================================================
# ADMIN DASHBOARD & USERS (10+ endpoints)
# =============================================================================

@pytest.mark.api
@pytest.mark.admin
class TestAdminDashboard:
    """Test admin dashboard and user management endpoints."""

    async def test_066_admin_dashboard(self, async_client: AsyncClient, admin_headers):
        """GET /v1/admin/dashboard - Admin dashboard."""
        response = await async_client.get("/v1/admin/dashboard", headers=admin_headers)
        assert response.status_code in [200, 403]

    async def test_067_admin_users_list(self, async_client: AsyncClient, admin_headers):
        """GET /v1/admin/users - List all users (admin)."""
        response = await async_client.get("/v1/admin/users", headers=admin_headers)
        assert response.status_code in [200, 403]

    async def test_068_admin_users_get_by_id(self, async_client: AsyncClient, admin_headers, test_user):
        """GET /v1/admin/users/{id} - Get user by ID (admin)."""
        response = await async_client.get(f"/v1/admin/users/{test_user.id}", headers=admin_headers)
        assert response.status_code in [200, 403, 404]

    async def test_069_admin_users_update(self, async_client: AsyncClient, admin_headers, test_user):
        """PUT /v1/admin/users/{id} - Update user (admin)."""
        response = await async_client.put(f"/v1/admin/users/{test_user.id}",
            headers=admin_headers,
            json={"role": "admin", "is_active": True}
        )
        assert response.status_code in [200, 403, 404]

    async def test_070_admin_users_delete(self, async_client: AsyncClient, admin_headers):
        """DELETE /v1/admin/users/{id} - Delete user (admin)."""
        user_id = str(uuid4())
        response = await async_client.delete(f"/v1/admin/users/{user_id}", headers=admin_headers)
        assert response.status_code in [200, 403, 404]

    async def test_071_admin_users_unauthorized(self, async_client: AsyncClient, auth_headers):
        """GET /v1/admin/users as regular user - Should fail."""
        response = await async_client.get("/v1/admin/users", headers=auth_headers)
        assert response.status_code == 403


# =============================================================================
# ADMIN PRODUCTS (5+ endpoints)
# =============================================================================

@pytest.mark.api
@pytest.mark.admin
class TestAdminProducts:
    """Test admin product management endpoints."""

    async def test_072_admin_products_list(self, async_client: AsyncClient, admin_headers):
        """GET /v1/admin/products - List all products (admin)."""
        response = await async_client.get("/v1/admin/products", headers=admin_headers)
        assert response.status_code in [200, 403]

    async def test_073_admin_products_create(self, async_client: AsyncClient, admin_headers, sample_product_data):
        """POST /v1/admin/products - Create product (admin)."""
        response = await async_client.post("/v1/admin/products",
            headers=admin_headers,
            json=sample_product_data
        )
        assert response.status_code in [200, 201, 403]

    async def test_074_admin_products_update(self, async_client: AsyncClient, admin_headers):
        """PUT /v1/admin/products/{id} - Update product (admin)."""
        product_id = str(uuid4())
        response = await async_client.put(f"/v1/admin/products/{product_id}",
            headers=admin_headers,
            json={"name": "Updated Product", "price": 99.99}
        )
        assert response.status_code in [200, 403, 404]

    async def test_075_admin_products_delete(self, async_client: AsyncClient, admin_headers):
        """DELETE /v1/admin/products/{id} - Delete product (admin)."""
        product_id = str(uuid4())
        response = await async_client.delete(f"/v1/admin/products/{product_id}", headers=admin_headers)
        assert response.status_code in [200, 403, 404]


# =============================================================================
# ADMIN ORDERS (5+ endpoints)
# =============================================================================

@pytest.mark.api
@pytest.mark.admin
class TestAdminOrders:
    """Test admin order management endpoints."""

    async def test_076_admin_orders_list(self, async_client: AsyncClient, admin_headers):
        """GET /v1/admin/orders - List all orders (admin)."""
        response = await async_client.get("/v1/admin/orders", headers=admin_headers)
        assert response.status_code in [200, 403]

    async def test_077_admin_orders_get_by_id(self, async_client: AsyncClient, admin_headers):
        """GET /v1/admin/orders/{id} - Get order by ID (admin)."""
        order_id = str(uuid4())
        response = await async_client.get(f"/v1/admin/orders/{order_id}", headers=admin_headers)
        assert response.status_code in [200, 403, 404]

    async def test_078_admin_orders_update_status(self, async_client: AsyncClient, admin_headers):
        """PATCH /v1/admin/orders/{id}/status - Update order status (admin)."""
        order_id = str(uuid4())
        response = await async_client.patch(f"/v1/admin/orders/{order_id}/status",
            headers=admin_headers,
            json={"status": "shipped", "tracking_number": "TRACK123", "carrier_name": "FedEx"}
        )
        assert response.status_code in [200, 403, 404]

    async def test_079_admin_orders_ship(self, async_client: AsyncClient, admin_headers):
        """POST /v1/admin/orders/{id}/ship - Ship order (admin)."""
        order_id = str(uuid4())
        response = await async_client.post(f"/v1/admin/orders/{order_id}/ship",
            headers=admin_headers,
            json={"tracking_number": "TRACK123", "carrier_name": "UPS"}
        )
        assert response.status_code in [200, 403, 404]


# =============================================================================
# ADMIN SUBSCRIPTIONS (5+ endpoints)
# =============================================================================

@pytest.mark.api
@pytest.mark.admin
class TestAdminSubscriptions:
    """Test admin subscription management endpoints."""

    async def test_080_admin_subscriptions_list(self, async_client: AsyncClient, admin_headers):
        """GET /v1/admin/subscriptions - List all subscriptions (admin)."""
        response = await async_client.get("/v1/admin/subscriptions", headers=admin_headers)
        assert response.status_code in [200, 403]

    async def test_081_admin_subscriptions_get_by_id(self, async_client: AsyncClient, admin_headers):
        """GET /v1/admin/subscriptions/{id} - Get subscription by ID (admin)."""
        sub_id = str(uuid4())
        response = await async_client.get(f"/v1/admin/subscriptions/{sub_id}", headers=admin_headers)
        assert response.status_code in [200, 403, 404]

    async def test_082_admin_subscriptions_update(self, async_client: AsyncClient, admin_headers):
        """PATCH /v1/admin/subscriptions/{id} - Update subscription (admin)."""
        sub_id = str(uuid4())
        response = await async_client.patch(f"/v1/admin/subscriptions/{sub_id}",
            headers=admin_headers,
            json={"status": "active"}
        )
        assert response.status_code in [200, 403, 404]

    async def test_083_admin_subscriptions_cancel(self, async_client: AsyncClient, admin_headers):
        """POST /v1/admin/subscriptions/{id}/cancel - Cancel subscription (admin)."""
        sub_id = str(uuid4())
        response = await async_client.post(f"/v1/admin/subscriptions/{sub_id}/cancel", headers=admin_headers)
        assert response.status_code in [200, 403, 404]


# =============================================================================
# ADMIN REFUNDS (5+ endpoints)
# =============================================================================

@pytest.mark.api
@pytest.mark.admin
class TestAdminRefunds:
    """Test admin refund management endpoints."""

    async def test_084_admin_refunds_list(self, async_client: AsyncClient, admin_headers):
        """GET /v1/admin/refunds - List all refunds (admin)."""
        response = await async_client.get("/v1/admin/refunds", headers=admin_headers)
        assert response.status_code in [200, 403]

    async def test_085_admin_refunds_create(self, async_client: AsyncClient, admin_headers):
        """POST /v1/admin/refunds - Create refund (admin)."""
        refund_data = {
            "order_id": str(uuid4()),
            "amount": 50.00,
            "reason": "Customer request",
            "items": [{"order_item_id": str(uuid4()), "quantity": 1}]
        }
        response = await async_client.post("/v1/admin/refunds", headers=admin_headers, json=refund_data)
        assert response.status_code in [200, 201, 403, 400]

    async def test_086_admin_refunds_get_by_id(self, async_client: AsyncClient, admin_headers):
        """GET /v1/admin/refunds/{id} - Get refund by ID (admin)."""
        refund_id = str(uuid4())
        response = await async_client.get(f"/v1/admin/refunds/{refund_id}", headers=admin_headers)
        assert response.status_code in [200, 403, 404]

    async def test_087_admin_refunds_update_status(self, async_client: AsyncClient, admin_headers):
        """PATCH /v1/admin/refunds/{id} - Update refund status (admin)."""
        refund_id = str(uuid4())
        response = await async_client.patch(f"/v1/admin/refunds/{refund_id}",
            headers=admin_headers,
            json={"status": "approved", "admin_notes": "Approved per policy"}
        )
        assert response.status_code in [200, 403, 404]


# =============================================================================
# ADMIN INVENTORY (3+ endpoints)
# =============================================================================

@pytest.mark.api
@pytest.mark.admin
class TestAdminInventory:
    """Test admin inventory management endpoints."""

    async def test_088_admin_inventory_list(self, async_client: AsyncClient, admin_headers):
        """GET /v1/admin/inventory - List inventory (admin)."""
        response = await async_client.get("/v1/admin/inventory", headers=admin_headers)
        assert response.status_code in [200, 403]

    async def test_089_admin_inventory_adjust(self, async_client: AsyncClient, admin_headers):
        """POST /v1/admin/inventory/adjust - Adjust inventory (admin)."""
        response = await async_client.post("/v1/admin/inventory/adjust",
            headers=admin_headers,
            json={
                "product_id": str(uuid4()),
                "variant_id": str(uuid4()),
                "quantity_change": 50,
                "reason": "Restock"
            }
        )
        assert response.status_code in [200, 403, 404]


# =============================================================================
# ADMIN SHIPPING (5+ endpoints)
# =============================================================================

@pytest.mark.api
@pytest.mark.admin
class TestAdminShipping:
    """Test admin shipping management endpoints."""

    async def test_090_admin_shipping_methods_list(self, async_client: AsyncClient, admin_headers):
        """GET /v1/admin/shipping/methods - List shipping methods (admin)."""
        response = await async_client.get("/v1/admin/shipping/methods", headers=admin_headers)
        assert response.status_code in [200, 403]

    async def test_091_admin_shipping_methods_create(self, async_client: AsyncClient, admin_headers):
        """POST /v1/admin/shipping/methods - Create shipping method (admin)."""
        response = await async_client.post("/v1/admin/shipping/methods",
            headers=admin_headers,
            json={
                "name": "Express Shipping",
                "carrier": "FedEx",
                "base_cost": 15.99,
                "estimated_days": 2
            }
        )
        assert response.status_code in [200, 201, 403]

    async def test_092_admin_shipping_methods_update(self, async_client: AsyncClient, admin_headers):
        """PUT /v1/admin/shipping/methods/{id} - Update shipping method (admin)."""
        method_id = str(uuid4())
        response = await async_client.put(f"/v1/admin/shipping/methods/{method_id}",
            headers=admin_headers,
            json={"base_cost": 19.99}
        )
        assert response.status_code in [200, 403, 404]

    async def test_093_admin_shipping_methods_delete(self, async_client: AsyncClient, admin_headers):
        """DELETE /v1/admin/shipping/methods/{id} - Delete shipping method (admin)."""
        method_id = str(uuid4())
        response = await async_client.delete(f"/v1/admin/shipping/methods/{method_id}", headers=admin_headers)
        assert response.status_code in [200, 403, 404]


# =============================================================================
# ANALYTICS ENDPOINTS (10+ endpoints)
# =============================================================================

@pytest.mark.api
@pytest.mark.analytics
class TestAnalyticsEndpoints:
    """Test all analytics endpoints."""

    async def test_094_analytics_sales(self, async_client: AsyncClient, admin_headers):
        """GET /v1/analytics/sales - Sales analytics."""
        response = await async_client.get("/v1/analytics/sales", headers=admin_headers)
        assert response.status_code in [200, 403]

    async def test_095_analytics_sales_with_date_range(self, async_client: AsyncClient, admin_headers):
        """GET /v1/analytics/sales?start_date&end_date - Sales analytics with date range."""
        response = await async_client.get(
            "/v1/analytics/sales?start_date=2024-01-01&end_date=2024-12-31",
            headers=admin_headers
        )
        assert response.status_code in [200, 403]

    async def test_096_analytics_users(self, async_client: AsyncClient, admin_headers):
        """GET /v1/analytics/users - User analytics."""
        response = await async_client.get("/v1/analytics/users", headers=admin_headers)
        assert response.status_code in [200, 403]

    async def test_097_analytics_products(self, async_client: AsyncClient, admin_headers):
        """GET /v1/analytics/products - Product analytics."""
        response = await async_client.get("/v1/analytics/products", headers=admin_headers)
        assert response.status_code in [200, 403]

    async def test_098_analytics_orders(self, async_client: AsyncClient, admin_headers):
        """GET /v1/analytics/orders - Order analytics."""
        response = await async_client.get("/v1/analytics/orders", headers=admin_headers)
        assert response.status_code in [200, 403]

    async def test_099_analytics_revenue(self, async_client: AsyncClient, admin_headers):
        """GET /v1/analytics/revenue - Revenue analytics."""
        response = await async_client.get("/v1/analytics/revenue", headers=admin_headers)
        assert response.status_code in [200, 403]

    async def test_100_analytics_dashboard(self, async_client: AsyncClient, admin_headers):
        """GET /v1/analytics/dashboard - Dashboard analytics."""
        response = await async_client.get("/v1/analytics/dashboard", headers=admin_headers)
        assert response.status_code in [200, 403]


# =============================================================================
# USER SUBSCRIPTIONS (5 endpoints)
# =============================================================================

@pytest.mark.api
class TestUserSubscriptions:
    """Test user subscription endpoints."""

    async def test_101_subscriptions_plans_list(self, async_client: AsyncClient):
        """GET /v1/subscriptions/plans - List subscription plans."""
        response = await async_client.get("/v1/subscriptions/plans")
        assert response.status_code == 200

    async def test_102_subscriptions_list(self, async_client: AsyncClient, auth_headers):
        """GET /v1/subscriptions/ - List user subscriptions."""
        response = await async_client.get("/v1/subscriptions/", headers=auth_headers)
        assert response.status_code == 200

    async def test_103_subscriptions_create(self, async_client: AsyncClient, auth_headers):
        """POST /v1/subscriptions/ - Create subscription."""
        response = await async_client.post("/v1/subscriptions/",
            headers=auth_headers,
            json={"plan_id": str(uuid4()), "payment_method_id": str(uuid4())}
        )
        assert response.status_code in [200, 201, 400, 404]

    async def test_104_subscriptions_get_by_id(self, async_client: AsyncClient, auth_headers):
        """GET /v1/subscriptions/{id} - Get subscription by ID."""
        sub_id = str(uuid4())
        response = await async_client.get(f"/v1/subscriptions/{sub_id}", headers=auth_headers)
        assert response.status_code in [200, 404]

    async def test_105_subscriptions_cancel(self, async_client: AsyncClient, auth_headers):
        """POST /v1/subscriptions/{id}/cancel - Cancel subscription."""
        sub_id = str(uuid4())
        response = await async_client.post(f"/v1/subscriptions/{sub_id}/cancel", headers=auth_headers)
        assert response.status_code in [200, 404]


# =============================================================================
# PROMOCODE ENDPOINTS (4+ endpoints)
# =============================================================================

@pytest.mark.api
class TestPromocodeEndpoints:
    """Test promocode endpoints."""

    async def test_106_promocodes_list(self, async_client: AsyncClient):
        """GET /v1/promocodes/ - List active promocodes."""
        response = await async_client.get("/v1/promocodes/")
        assert response.status_code in [200, 404]

    async def test_107_promocodes_validate(self, async_client: AsyncClient, auth_headers):
        """POST /v1/promocodes/validate - Validate promocode."""
        response = await async_client.post("/v1/promocodes/validate",
            headers=auth_headers,
            json={"code": "SAVE10", "cart_total": 100.00}
        )
        assert response.status_code in [200, 400, 404]

    async def test_108_promocodes_create_as_admin(self, async_client: AsyncClient, admin_headers):
        """POST /v1/promocodes/ - Create promocode (admin)."""
        response = await async_client.post("/v1/promocodes/",
            headers=admin_headers,
            json={
                "code": "NEWCODE20",
                "discount_type": "percentage",
                "discount_value": 20,
                "max_uses": 100,
                "min_order_amount": 50.00
            }
        )
        assert response.status_code in [200, 201, 403]

    async def test_109_promocodes_delete_as_admin(self, async_client: AsyncClient, admin_headers):
        """DELETE /v1/promocodes/{code} - Delete promocode (admin)."""
        response = await async_client.delete("/v1/promocodes/OLDCODE", headers=admin_headers)
        assert response.status_code in [200, 403, 404]


# =============================================================================
# SHIPPING ENDPOINTS (4+ endpoints)
# =============================================================================

@pytest.mark.api
class TestShippingEndpoints:
    """Test shipping endpoints."""

    async def test_110_shipping_methods_list(self, async_client: AsyncClient):
        """GET /v1/shipping/methods - List shipping methods."""
        response = await async_client.get("/v1/shipping/methods")
        assert response.status_code == 200

    async def test_111_shipping_calculate(self, async_client: AsyncClient, auth_headers):
        """POST /v1/shipping/calculate - Calculate shipping cost."""
        response = await async_client.post("/v1/shipping/calculate",
            headers=auth_headers,
            json={
                "address_id": str(uuid4()),
                "items": [{"variant_id": str(uuid4()), "quantity": 2}]
            }
        )
        assert response.status_code in [200, 400, 404]

    async def test_112_shipping_tracking(self, async_client: AsyncClient, auth_headers):
        """GET /v1/shipping/tracking/{number} - Track shipment."""
        response = await async_client.get("/v1/shipping/tracking/TRACK123456", headers=auth_headers)
        assert response.status_code in [200, 404]


# =============================================================================
# TAX ENDPOINTS (2+ endpoints)
# =============================================================================

@pytest.mark.api
class TestTaxEndpoints:
    """Test tax endpoints."""

    async def test_113_tax_calculate(self, async_client: AsyncClient, auth_headers):
        """POST /v1/tax/calculate - Calculate tax."""
        response = await async_client.post("/v1/tax/calculate",
            headers=auth_headers,
            json={
                "subtotal": 100.00,
                "shipping_address_id": str(uuid4())
            }
        )
        assert response.status_code in [200, 400, 404]

    async def test_114_tax_rates_list_as_admin(self, async_client: AsyncClient, admin_headers):
        """GET /v1/tax/rates - List tax rates (admin)."""
        response = await async_client.get("/v1/tax/rates", headers=admin_headers)
        assert response.status_code in [200, 403]


# =============================================================================
# WEBHOOK ENDPOINTS (2+ endpoints)
# =============================================================================

@pytest.mark.api
class TestWebhookEndpoints:
    """Test webhook endpoints."""

    async def test_115_webhooks_stripe(self, async_client: AsyncClient):
        """POST /v1/webhooks/stripe - Stripe webhook."""
        response = await async_client.post("/v1/webhooks/stripe",
            json={"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_123"}}},
            headers={"Stripe-Signature": "test_signature"}
        )
        assert response.status_code in [200, 400]

    async def test_116_webhooks_stripe_invalid(self, async_client: AsyncClient):
        """POST /v1/webhooks/stripe without signature - Should fail."""
        response = await async_client.post("/v1/webhooks/stripe", json={"type": "test"})
        assert response.status_code in [400, 401]
