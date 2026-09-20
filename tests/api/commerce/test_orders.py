"""API endpoint tests - see conftest.py for shared fixtures."""

import pytest
from httpx import AsyncClient
from uuid import uuid4, UUID
from typing import Dict, Any

@pytest.mark.api
class TestOrderEndpoints:
    """Test all order endpoints."""

    async def test_056_orders_list(self, async_client: AsyncClient, auth_headers):
        """GET /v1/orders/ - List orders."""
        response = await async_client.get("/v1/orders/", headers=auth_headers)
        assert response.status_code == 200

    async def test_057_orders_get_by_id(self, async_client: AsyncClient, auth_headers):
        """GET /v1/orders/{id} - Get order by ID."""
        order_id = str(uuid4())
        response = await async_client.get(f"/v1/orders/{order_id}/", headers=auth_headers)
        assert response.status_code in [200, 404]

    async def test_058_orders_cancel(self, async_client: AsyncClient, auth_headers):
        """POST /v1/orders/{id}/cancel - Cancel order."""
        order_id = str(uuid4())
        response = await async_client.post(f"/v1/orders/{order_id}/cancel/",
            headers=auth_headers,
            json={"reason": "Changed my mind"}
        )
        assert response.status_code in [200, 400, 404]

    async def test_059_orders_get_tracking(self, async_client: AsyncClient, auth_headers):
        """GET /v1/orders/{id}/tracking - Get order tracking."""
        order_id = str(uuid4())
        response = await async_client.get(f"/v1/orders/{order_id}/tracking/", headers=auth_headers)
        assert response.status_code in [200, 404]


# =============================================================================
# PAYMENT ENDPOINTS (8+ endpoints)
# =============================================================================

