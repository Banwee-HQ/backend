"""API endpoint tests - see conftest.py for shared fixtures."""

import pytest
from httpx import AsyncClient
from uuid import uuid4, UUID
from typing import Dict, Any

from services.commerce.webhooks import WebhookService

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

    async def test_webhooks_stripe_verified_event_returns_success_envelope(self, async_client: AsyncClient, mocker):
        """POST /v1/webhooks/stripe - A signature that verifies (mocking only Stripe's own
        construct_event, per this repo's established webhook-test pattern - see
        tests/services/commerce/test_webhooks.py) reaches the success return path."""
        fake_event = {
            "id": "evt_api_test", "type": "customer.created", "created": 12345,
            "data": {"object": {}},
        }
        mocker.patch("stripe.Webhook.construct_event", return_value=fake_event)
        response = await async_client.post("/v1/webhooks/stripe/",
            content=b'{"any": "payload"}', headers={"stripe-signature": "sig", "content-type": "application/json"})
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "success"
        assert data["event_id"] == "evt_api_test"

    async def test_webhooks_stripe_unexpected_error_returns_500(self, async_client: AsyncClient, mocker):
        """POST /v1/webhooks/stripe - An unexpected (non-HTTPException) error anywhere in
        webhook processing must be caught and turned into a generic 500, never leak raw."""
        mocker.patch.object(WebhookService, "handle_stripe_webhook", side_effect=RuntimeError("boom"))
        response = await async_client.post("/v1/webhooks/stripe/",
            content=b'{"any": "payload"}', headers={"stripe-signature": "sig", "content-type": "application/json"})
        assert response.status_code == 500
