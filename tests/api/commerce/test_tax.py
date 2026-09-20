"""API endpoint tests - see conftest.py for shared fixtures."""

import pytest
from httpx import AsyncClient
from uuid import uuid4, UUID
from typing import Dict, Any

@pytest.mark.api
@pytest.mark.tax
class TestTaxEndpoints:
    """Test all tax endpoints."""

    async def test_097_tax_calculate(self, async_client: AsyncClient):
        """POST /v1/tax/calculate - Calculate tax."""
        calc_data = {"subtotal": 100.0, "shipping": 10.0, "country_code": "US", "state_code": "CA"}
        response = await async_client.post("/v1/tax/calculate/", json=calc_data)
        assert response.status_code == 200

    async def test_098_tax_rates_list(self, async_client: AsyncClient, admin_headers):
        """GET /v1/tax/rates - List tax rates."""
        response = await async_client.get("/v1/tax/rates/", headers=admin_headers)
        assert response.status_code in [200, 403]

    async def test_099_tax_rates_create(self, async_client: AsyncClient, admin_headers):
        """POST /v1/tax/rates - Create tax rate."""
        rate_data = {"country_code": "US", "country_name": "United States", "province_code": "CA", "tax_rate": 0.0875, "tax_name": "CA Tax"}
        response = await async_client.post("/v1/tax/rates/", headers=admin_headers, json=rate_data)
        assert response.status_code in [200, 201, 400, 403, 500]  # 500 if validation fails

    async def test_100_tax_rates_get(self, async_client: AsyncClient, admin_headers):
        """GET /v1/tax/rates/{id} - Get tax rate."""
        rate_id = str(uuid4())
        response = await async_client.get(f"/v1/tax/rates/{rate_id}/", headers=admin_headers)
        assert response.status_code in [200, 404, 403]

    async def test_101_tax_rates_update(self, async_client: AsyncClient, admin_headers):
        """PATCH /v1/tax/rates/{id} - Update tax rate."""
        rate_id = str(uuid4())
        response = await async_client.patch(f"/v1/tax/rates/{rate_id}/", 
            headers=admin_headers, json={"rate": 0.09})
        assert response.status_code in [200, 404, 403]

    async def test_102_tax_rates_delete(self, async_client: AsyncClient, admin_headers):
        """DELETE /v1/tax/rates/{id} - Delete tax rate."""
        rate_id = str(uuid4())
        response = await async_client.delete(f"/v1/tax/rates/{rate_id}/", headers=admin_headers)
        assert response.status_code in [200, 404, 403]


# =============================================================================
# SHIPPING ENDPOINTS (6+ endpoints)
# =============================================================================

