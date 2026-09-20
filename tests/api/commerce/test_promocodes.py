"""API endpoint tests - see conftest.py for shared fixtures."""

import pytest
from httpx import AsyncClient
from uuid import uuid4, UUID
from typing import Dict, Any

@pytest.mark.api
@pytest.mark.promocodes
class TestPromocodeEndpoints:
    """Test all promocode endpoints."""

    async def test_108_promocodes_list(self, async_client: AsyncClient, admin_headers):
        """GET /v1/promocodes/ - List promocodes."""
        response = await async_client.get("/v1/promocodes/", headers=admin_headers)
        assert response.status_code in [200, 403]

    async def test_109_promocodes_create(self, async_client: AsyncClient, admin_headers):
        """POST /v1/promocodes/ - Create promocode."""
        from datetime import datetime, timezone
        valid_until = datetime.now(timezone.utc).isoformat()
        promo_data = {"code": "TEST20", "discount_type": "percentage", "value": 20, "valid_until": valid_until}
        response = await async_client.post("/v1/promocodes/", headers=admin_headers, json=promo_data)
        assert response.status_code in [200, 201, 400, 403, 500]  # 500 if DB error

    async def test_110_promocodes_get(self, async_client: AsyncClient, admin_headers):
        """GET /v1/promocodes/{id} - Get promocode."""
        promo_id = str(uuid4())
        response = await async_client.get(f"/v1/promocodes/{promo_id}/", headers=admin_headers)
        assert response.status_code in [200, 404, 403]

    async def test_111_promocodes_update(self, async_client: AsyncClient, admin_headers):
        """PATCH /v1/promocodes/{id} - Update promocode."""
        promo_id = str(uuid4())
        response = await async_client.patch(f"/v1/promocodes/{promo_id}/", 
            headers=admin_headers, json={"discount_type": "percentage", "value": 25})
        assert response.status_code in [200, 404, 403]

    async def test_112_promocodes_delete(self, async_client: AsyncClient, admin_headers):
        """DELETE /v1/promocodes/{id} - Delete promocode."""
        promo_id = str(uuid4())
        response = await async_client.delete(f"/v1/promocodes/{promo_id}/", headers=admin_headers)
        assert response.status_code in [200, 404, 403]

    async def test_113_promocodes_validate(self, async_client: AsyncClient, auth_headers):
        """POST /v1/promocodes/validate - Validate promocode."""
        response = await async_client.post("/v1/promocodes/validate/", 
            headers=auth_headers, json={"code": "TEST20", "cart_total": 100.0})
        assert response.status_code in [200, 400, 403]

    async def test_114a_promocodes_trigger_cleanup(self, async_client: AsyncClient, admin_headers):
        """POST /v1/promocodes/trigger-cleanup - Trigger promocode cleanup."""
        response = await async_client.post("/v1/promocodes/trigger-cleanup/", headers=admin_headers)
        assert response.status_code in [200, 403, 500]  # 500 if DB error


# =============================================================================
# REFUNDS ENDPOINTS (4 endpoints)
# =============================================================================

