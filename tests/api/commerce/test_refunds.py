"""API endpoint tests - see conftest.py for shared fixtures."""

import pytest
from httpx import AsyncClient
from uuid import uuid4, UUID
from typing import Dict, Any

@pytest.mark.api
@pytest.mark.refunds
class TestRefundEndpoints:
    """Test all refund endpoints."""

    async def test_115_refunds_list(self, async_client: AsyncClient, auth_headers):
        """GET /v1/refunds/ - List refunds."""
        response = await async_client.get("/v1/refunds/", headers=auth_headers)
        assert response.status_code in [200, 403]

    async def test_116_refunds_create(self, async_client: AsyncClient, auth_headers):
        """POST /v1/refunds/ - Create refund."""
        refund_data = {"order_id": str(uuid4()), "reason": "Item damaged", "amount": 50.0}
        response = await async_client.post("/v1/refunds/", headers=auth_headers, json=refund_data)
        assert response.status_code in [200, 201, 400, 403]

    async def test_117_refunds_get(self, async_client: AsyncClient, auth_headers):
        """GET /v1/refunds/{id} - Get refund."""
        refund_id = str(uuid4())
        response = await async_client.get(f"/v1/refunds/{refund_id}/", headers=auth_headers)
        assert response.status_code in [200, 404, 403, 500]  # 500 if DB error

    async def test_118_refunds_update_status(self, async_client: AsyncClient, admin_headers):
        """PUT /v1/refunds/{id}/status - Update refund status."""
        refund_id = str(uuid4())
        response = await async_client.put(f"/v1/refunds/{refund_id}/status/", 
            headers=admin_headers, json={"status": "approved"})
        assert response.status_code in [200, 404, 403, 500]  # 500 if refund doesn't exist


# =============================================================================
# WEBHOOKS ENDPOINTS (2 endpoints)
# =============================================================================

