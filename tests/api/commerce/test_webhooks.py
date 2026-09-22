"""API endpoint tests - see conftest.py for shared fixtures."""

import pytest
from httpx import AsyncClient
from uuid import uuid4, UUID
from typing import Dict, Any

@pytest.mark.api
@pytest.mark.webhooks
class TestWebhookEndpoints:
    """Test webhook endpoints."""

    async def test_119_webhooks_stripe_invalid_signature(self, async_client: AsyncClient):
        """POST /v1/webhooks/stripe - A forged/invalid signature is rejected outright."""
        payload = {"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_test"}}}
        response = await async_client.post("/v1/webhooks/stripe/",
            json=payload, headers={"stripe-signature": "test_sig"})
        assert response.status_code == 401

    async def test_webhooks_stripe_missing_signature(self, async_client: AsyncClient):
        """POST /v1/webhooks/stripe - No stripe-signature header at all."""
        response = await async_client.post("/v1/webhooks/stripe/",
            json={"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_test"}}})
        assert response.status_code == 400

    async def test_120_webhooks_health(self, async_client: AsyncClient):
        """GET /v1/webhooks/health - Webhook health check."""
        response = await async_client.get("/v1/webhooks/health/")
        assert response.status_code == 200
