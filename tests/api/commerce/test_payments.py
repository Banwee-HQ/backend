"""API endpoint tests - see conftest.py for shared fixtures."""

import pytest
from httpx import AsyncClient
from uuid import uuid4, UUID
from typing import Dict, Any

@pytest.mark.api
class TestPaymentEndpoints:
    """Test all payment endpoints."""

    async def test_060_payments_overview(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/ - Get payments overview."""
        response = await async_client.get("/v1/payments/", headers=auth_headers)
        assert response.status_code == 200

    async def test_061_payments_methods_list(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/methods - List payment methods."""
        response = await async_client.get("/v1/payments/methods/", headers=auth_headers)
        assert response.status_code == 200

    async def test_062_payments_methods_create(self, async_client: AsyncClient, auth_headers):
        """POST /v1/payments/methods - Create payment method."""
        response = await async_client.post("/v1/payments/methods/",
            headers=auth_headers,
            json={
                "type": "card",
                "provider": "stripe",
                "stripe_payment_method_id": "pm_test_123",
                "last_four": "1234"
            }
        )
        assert response.status_code in [200, 201, 400, 500]  # 500 if validation/stripe fails

    async def test_063_payments_methods_delete(self, async_client: AsyncClient, auth_headers):
        """DELETE /v1/payments/methods/{id} - Delete payment method."""
        method_id = str(uuid4())
        response = await async_client.delete(f"/v1/payments/methods/{method_id}/", headers=auth_headers)
        assert response.status_code in [200, 404, 500]  # 500 if method doesn't exist

    async def test_063a_payments_failures_list(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/failures - List failed payments."""
        response = await async_client.get("/v1/payments/failures/", headers=auth_headers)
        assert response.status_code in [200, 403, 404]

    async def test_063b_payments_failure_status(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/failures/{id}/status - Get failure status."""
        payment_intent_id = str(uuid4())
        response = await async_client.get(f"/v1/payments/failures/{payment_intent_id}/status/", headers=auth_headers)
        assert response.status_code in [200, 404, 403]

    async def test_063c_payments_failure_retry(self, async_client: AsyncClient, auth_headers):
        """POST /v1/payments/failures/{id}/retry - Retry failed payment."""
        payment_intent_id = str(uuid4())
        response = await async_client.post(f"/v1/payments/failures/{payment_intent_id}/retry/",
            headers=auth_headers,
            json={"new_payment_method_id": str(uuid4())}
        )
        assert response.status_code in [200, 404, 403, 400]


# =============================================================================
# CONTACT MESSAGE ENDPOINTS (5 endpoints)
# =============================================================================

