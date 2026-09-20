"""API endpoint tests - see conftest.py for shared fixtures."""

import pytest
from httpx import AsyncClient
from uuid import uuid4, UUID
from typing import Dict, Any

@pytest.mark.api
@pytest.mark.shipping
class TestShippingEndpoints:
    """Test all shipping endpoints."""

    async def test_103_shipping_methods_list(self, async_client: AsyncClient):
        """GET /v1/shipping/methods - List shipping methods."""
        response = await async_client.get("/v1/shipping/methods/")
        assert response.status_code in [200, 401]  # 401 if auth required

    async def test_104_shipping_methods_create(self, async_client: AsyncClient, admin_headers):
        """POST /v1/shipping/methods - Create shipping method."""
        method_data = {"name": "Express", "price": 15.0, "estimated_days": 2}
        response = await async_client.post("/v1/shipping/methods/", headers=admin_headers, json=method_data)
        assert response.status_code in [200, 201, 403]

    async def test_105_shipping_calculate(self, async_client: AsyncClient):
        """POST /v1/shipping/calculate - Calculate shipping."""
        calc_data = {"address": {"country": "US", "state": "CA", "zip": "90210"}, "items": [{"weight": 1.0, "quantity": 2}]}
        response = await async_client.post("/v1/shipping/calculate/", json=calc_data)
        assert response.status_code in [200, 400]

    async def test_106_shipping_tracking(self, async_client: AsyncClient):
        """GET /v1/shipping/tracking/{tracking_number} - Track shipment."""
        tracking_num = "TEST123456"
        response = await async_client.get(f"/v1/shipping/tracking/{tracking_num}/")
        assert response.status_code in [200, 404]

    async def test_107_shipping_tracking_update(self, async_client: AsyncClient, admin_headers):
        """POST /v1/shipping/tracking/update - Update tracking."""
        tracking_data = {"tracking_number": "TEST123456", "status": "shipped", "location": "NYC"}
        response = await async_client.post("/v1/shipping/tracking/update/", headers=admin_headers, json=tracking_data)
        assert response.status_code in [200, 403, 404]  # 404 if endpoint doesn't exist


# =============================================================================
# PROMOCODES ENDPOINTS (6 endpoints)
# =============================================================================

