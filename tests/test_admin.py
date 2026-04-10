"""Tests for admin and analytics endpoints."""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.api
@pytest.mark.unit
class TestAdminEndpoints:
    """Test admin management endpoints."""

    async def test_get_admin_dashboard(self, async_client: AsyncClient, admin_headers: dict):
        """Test getting admin dashboard data."""
        response = await async_client.get("/v1/admin/dashboard", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data

    async def test_get_admin_dashboard_unauthorized(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting admin dashboard as regular user."""
        response = await async_client.get("/v1/admin/dashboard", headers=auth_headers)
        assert response.status_code == 403

    async def test_get_admin_users(self, async_client: AsyncClient, admin_headers: dict):
        """Test getting all users as admin."""
        response = await async_client.get("/v1/admin/users", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data

    async def test_get_admin_user_by_id(self, async_client: AsyncClient, admin_headers: dict):
        """Test getting specific user as admin."""
        user_id = str(uuid4())
        response = await async_client.get(f"/v1/admin/users/{user_id}", headers=admin_headers)
        assert response.status_code in [200, 404]

    async def test_update_user_as_admin(self, async_client: AsyncClient, admin_headers: dict):
        """Test updating user as admin."""
        user_id = str(uuid4())
        update_data = {
            "role": "admin",
            "is_active": True
        }
        response = await async_client.patch(f"/v1/admin/users/{user_id}", headers=admin_headers, json=update_data)
        assert response.status_code in [200, 404]

    async def test_get_admin_products(self, async_client: AsyncClient, admin_headers: dict):
        """Test getting all products as admin."""
        response = await async_client.get("/v1/admin/products", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_create_product_as_admin(self, async_client: AsyncClient, admin_headers: dict, sample_product_data):
        """Test creating product as admin."""
        response = await async_client.post("/v1/admin/products", headers=admin_headers, json=sample_product_data)
        assert response.status_code in [200, 201]

    async def test_update_product_as_admin(self, async_client: AsyncClient, admin_headers: dict):
        """Test updating product as admin."""
        product_id = str(uuid4())
        update_data = {"price": 39.99, "is_active": True}
        response = await async_client.patch(f"/v1/admin/products/{product_id}", headers=admin_headers, json=update_data)
        assert response.status_code in [200, 404]

    async def test_delete_product_as_admin(self, async_client: AsyncClient, admin_headers: dict):
        """Test deleting product as admin."""
        product_id = str(uuid4())
        response = await async_client.delete(f"/v1/admin/products/{product_id}", headers=admin_headers)
        assert response.status_code in [200, 404]

    async def test_get_admin_orders(self, async_client: AsyncClient, admin_headers: dict):
        """Test getting all orders as admin."""
        response = await async_client.get("/v1/admin/orders", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_update_order_status_as_admin(self, async_client: AsyncClient, admin_headers: dict):
        """Test updating order status as admin."""
        order_id = str(uuid4())
        status_data = {"status": "shipped", "tracking_number": "TRACK123"}
        response = await async_client.patch(f"/v1/admin/orders/{order_id}/status", headers=admin_headers, json=status_data)
        assert response.status_code in [200, 404]


@pytest.mark.api
@pytest.mark.unit
class TestAnalyticsEndpoints:
    """Test analytics endpoints."""

    async def test_get_sales_analytics(self, async_client: AsyncClient, admin_headers: dict):
        """Test getting sales analytics."""
        response = await async_client.get("/v1/analytics/sales", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data

    async def test_get_sales_analytics_with_date_range(self, async_client: AsyncClient, admin_headers: dict):
        """Test getting sales analytics with date range."""
        response = await async_client.get(
            "/v1/analytics/sales?start_date=2024-01-01&end_date=2024-12-31",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_get_sales_analytics_unauthorized(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting analytics as regular user."""
        response = await async_client.get("/v1/analytics/sales", headers=auth_headers)
        assert response.status_code == 403

    async def test_get_user_analytics(self, async_client: AsyncClient, admin_headers: dict):
        """Test getting user analytics."""
        response = await async_client.get("/v1/analytics/users", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_get_product_analytics(self, async_client: AsyncClient, admin_headers: dict):
        """Test getting product analytics."""
        response = await async_client.get("/v1/analytics/products", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_get_order_analytics(self, async_client: AsyncClient, admin_headers: dict):
        """Test getting order analytics."""
        response = await async_client.get("/v1/analytics/orders", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_get_revenue_analytics(self, async_client: AsyncClient, admin_headers: dict):
        """Test getting revenue analytics."""
        response = await async_client.get("/v1/analytics/revenue", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_get_dashboard_summary(self, async_client: AsyncClient, admin_headers: dict):
        """Test getting dashboard summary."""
        response = await async_client.get("/v1/analytics/dashboard", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
