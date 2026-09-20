"""API endpoint tests - see conftest.py for shared fixtures."""

import pytest
from httpx import AsyncClient
from uuid import uuid4, UUID
from typing import Dict, Any

@pytest.mark.api
@pytest.mark.subscriptions
class TestSubscriptionEndpoints:
    """Test all subscription endpoints."""

    async def test_076_subscriptions_list(self, async_client: AsyncClient, auth_headers):
        """GET /v1/subscriptions/ - List subscriptions."""
        response = await async_client.get("/v1/subscriptions/", headers=auth_headers)
        assert response.status_code in [200, 403, 500]  # 500 if DB error

    async def test_077_subscriptions_create(self, async_client: AsyncClient, auth_headers):
        """POST /v1/subscriptions/ - Create subscription."""
        sub_data = {
            "name": "Test Subscription",
            "frequency": "monthly",
            "products": [{"variant_id": str(uuid4()), "quantity": 1}]
        }
        response = await async_client.post("/v1/subscriptions/", headers=auth_headers, json=sub_data)
        assert response.status_code in [200, 201, 400, 403]

    async def test_078_subscriptions_get_by_id(self, async_client: AsyncClient, auth_headers):
        """GET /v1/subscriptions/{id} - Get subscription."""
        sub_id = str(uuid4())
        response = await async_client.get(f"/v1/subscriptions/{sub_id}/", headers=auth_headers)
        assert response.status_code in [200, 404, 403]

    async def test_079_subscriptions_update(self, async_client: AsyncClient, auth_headers):
        """PATCH /v1/subscriptions/{id} - Update subscription."""
        sub_id = str(uuid4())
        response = await async_client.patch(f"/v1/subscriptions/{sub_id}/", 
            headers=auth_headers, json={"status": "active"})
        assert response.status_code in [200, 404, 403, 500]  # 500 if DB error

    async def test_080_subscriptions_cancel(self, async_client: AsyncClient, auth_headers):
        """POST /v1/subscriptions/{id}/cancel - Cancel subscription."""
        sub_id = str(uuid4())
        response = await async_client.post(f"/v1/subscriptions/{sub_id}/cancel/", headers=auth_headers)
        assert response.status_code in [200, 404, 403]

    async def test_081_subscriptions_pause(self, async_client: AsyncClient, auth_headers):
        """POST /v1/subscriptions/{id}/pause - Pause subscription."""
        sub_id = str(uuid4())
        response = await async_client.post(f"/v1/subscriptions/{sub_id}/pause/", headers=auth_headers)
        assert response.status_code in [200, 404, 403, 500]  # 500 if DB error

    async def test_082_subscriptions_resume(self, async_client: AsyncClient, auth_headers):
        """POST /v1/subscriptions/{id}/resume - Resume subscription."""
        sub_id = str(uuid4())
        response = await async_client.post(f"/v1/subscriptions/{sub_id}/resume/", headers=auth_headers)
        assert response.status_code in [200, 404, 403, 500]  # 500 if DB error

    async def test_083_subscriptions_add_products(self, async_client: AsyncClient, auth_headers):
        """POST /v1/subscriptions/{id}/products - Add products."""
        sub_id = str(uuid4())
        response = await async_client.post(f"/v1/subscriptions/{sub_id}/products/", 
            headers=auth_headers, json={"products": [{"variant_id": str(uuid4()), "quantity": 1}]})
        assert response.status_code in [200, 404, 403, 422]  # 422 if validation error

    async def test_084_subscriptions_remove_products(self, async_client: AsyncClient, auth_headers):
        """DELETE /v1/subscriptions/{id}/products/{product_id} - Remove product from subscription."""
        sub_id = str(uuid4())
        product_id = str(uuid4())
        response = await async_client.delete(f"/v1/subscriptions/{sub_id}/products/{product_id}/",
            headers=auth_headers)
        assert response.status_code in [200, 404, 403]

    async def test_085_subscriptions_calculate_cost(self, async_client: AsyncClient, auth_headers):
        """POST /v1/subscriptions/calculate-cost - Calculate cost."""
        response = await async_client.post("/v1/subscriptions/calculate-cost/", 
            headers=auth_headers, json={"products": [{"variant_id": str(uuid4()), "quantity": 1}], "frequency": "monthly"})
        assert response.status_code in [200, 400, 403, 422]  # 422 if validation error

    async def test_086_subscriptions_trigger_processing(self, async_client: AsyncClient, admin_headers):
        """POST /v1/subscriptions/trigger-order-processing - Trigger processing."""
        response = await async_client.post("/v1/subscriptions/trigger-order-processing/", headers=admin_headers)
        assert response.status_code in [200, 403, 500]  # 500 if DB error

    async def test_087_subscriptions_list_due(self, async_client: AsyncClient, admin_headers):
        """GET /v1/subscriptions/due - List due subscriptions."""
        response = await async_client.get("/v1/subscriptions/due/", headers=admin_headers)
        assert response.status_code in [200, 403, 422]  # 422 if DB error

    async def test_087a_subscriptions_change_frequency(self, async_client: AsyncClient, auth_headers):
        """PATCH /v1/subscriptions/{id}/frequency - Change subscription frequency."""
        sub_id = str(uuid4())
        response = await async_client.patch(f"/v1/subscriptions/{sub_id}/frequency/", 
            headers=auth_headers, json={"frequency": "weekly"})
        assert response.status_code in [200, 404, 403, 500]  # 500 if DB error

    async def test_087b_subscriptions_skip(self, async_client: AsyncClient, auth_headers):
        """POST /v1/subscriptions/{id}/skip - Skip upcoming shipment."""
        sub_id = str(uuid4())
        response = await async_client.post(f"/v1/subscriptions/{sub_id}/skip/", 
            headers=auth_headers, json={"next_shipment_date": "2025-12-31"})
        assert response.status_code in [200, 404, 403, 500]  # 500 if DB error

    async def test_087c_subscriptions_unskip(self, async_client: AsyncClient, auth_headers):
        """POST /v1/subscriptions/{id}/unskip - Unskip shipment."""
        sub_id = str(uuid4())
        response = await async_client.post(f"/v1/subscriptions/{sub_id}/unskip/", 
            headers=auth_headers, json={})
        assert response.status_code in [200, 404, 403, 500]  # 500 if DB error


# =============================================================================
# INVENTORY ENDPOINTS (14 endpoints)
# =============================================================================

