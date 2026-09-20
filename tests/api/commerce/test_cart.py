"""API endpoint tests - see conftest.py for shared fixtures."""

import pytest
from httpx import AsyncClient
from uuid import uuid4, UUID
from typing import Dict, Any

@pytest.mark.api
class TestCartEndpoints:
    """Test all 7 cart endpoints."""

    async def test_051_cart_get(self, async_client: AsyncClient, auth_headers):
        """GET /v1/cart/ - Get cart."""
        response = await async_client.get("/v1/cart/", headers=auth_headers)
        assert response.status_code == 200

    async def test_052_cart_add_item(self, async_client: AsyncClient, auth_headers):
        """POST /v1/cart/add - Add item to cart."""
        response = await async_client.post("/v1/cart/add/",
            headers=auth_headers,
            json={"variant_id": str(uuid4()), "quantity": 2}
        )
        assert response.status_code in [200, 400, 404]

    async def test_053_cart_update_item(self, async_client: AsyncClient, auth_headers):
        """PATCH /v1/cart/items/{id} - Update cart item."""
        item_id = str(uuid4())
        response = await async_client.patch(f"/v1/cart/items/{item_id}/",
            headers=auth_headers,
            json={"quantity": 5}
        )
        assert response.status_code in [200, 404]

    async def test_054_cart_remove_item(self, async_client: AsyncClient, auth_headers):
        """DELETE /v1/cart/items/{id} - Remove cart item."""
        item_id = str(uuid4())
        response = await async_client.delete(f"/v1/cart/items/{item_id}/", headers=auth_headers)
        assert response.status_code in [200, 404]

    async def test_055_cart_clear(self, async_client: AsyncClient, auth_headers):
        """POST /v1/cart/clear - Clear cart."""
        response = await async_client.post("/v1/cart/clear/", headers=auth_headers)
        assert response.status_code in [200, 201]

    async def test_055a_cart_calculate(self, async_client: AsyncClient, auth_headers):
        """POST /v1/cart/calculate - Calculate cart totals."""
        response = await async_client.post("/v1/cart/calculate/",
            headers=auth_headers,
            json={"items": [{"variant_id": str(uuid4()), "quantity": 2}]}
        )
        assert response.status_code in [200, 400]

    async def test_055b_cart_checkout_summary(self, async_client: AsyncClient, auth_headers):
        """GET /v1/cart/checkout-summary - Get checkout summary."""
        response = await async_client.get("/v1/cart/checkout-summary/", headers=auth_headers)
        assert response.status_code in [200, 400]


# =============================================================================
# ORDER ENDPOINTS (8+ endpoints)
# =============================================================================

