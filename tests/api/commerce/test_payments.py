"""Tests for api/commerce/payments.py - /v1/payments endpoints.

Uses Stripe's real test-mode API rather than mocking - .env.dev has a sk_test_
key, so these hit Stripe's test environment for real without touching any
actual card or charging money. stripe.PaymentMethod.create() with tok_visa is
used (not the shared named token pm_card_visa) because the app stores whatever
ID it's given as a unique column - reusing the same shared token across tests
collides on that uniqueness constraint.
"""

import os
import pytest
import stripe
from httpx import AsyncClient
from uuid import uuid4

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")


def fresh_stripe_payment_method_id() -> str:
    return stripe.PaymentMethod.create(type="card", card={"token": "tok_visa"}).id


@pytest.fixture
async def created_method(async_client: AsyncClient, auth_headers):
    response = await async_client.post("/v1/payments/methods/", headers=auth_headers, json={
        "type": "card", "stripe_payment_method_id": fresh_stripe_payment_method_id(), "is_default": True
    })
    return response.json()["data"]


@pytest.mark.api
class TestPaymentMethodEndpoints:

    async def test_overview(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/ - Overview endpoint."""
        response = await async_client.get("/v1/payments/", headers=auth_headers)
        assert response.status_code == 200

    async def test_list_empty(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/methods - A new user has no payment methods."""
        response = await async_client.get("/v1/payments/methods/", headers=auth_headers)
        assert response.status_code == 200

    async def test_create(self, async_client: AsyncClient, auth_headers):
        """POST /v1/payments/methods - Create payment method from a real Stripe test card."""
        response = await async_client.post("/v1/payments/methods/", headers=auth_headers, json={
            "type": "card", "stripe_payment_method_id": fresh_stripe_payment_method_id(), "is_default": True
        })
        assert response.status_code == 201
        assert response.json()["data"]["last_four"] == "4242"

    async def test_get_by_id(self, async_client: AsyncClient, auth_headers, created_method):
        """GET /v1/payments/methods/{id} - Get a specific method."""
        response = await async_client.get(f"/v1/payments/methods/{created_method['id']}/", headers=auth_headers)
        assert response.status_code == 200

    async def test_get_by_id_not_found(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/methods/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/payments/methods/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 404

    async def test_set_default(self, async_client: AsyncClient, auth_headers, created_method):
        """POST /v1/payments/methods/{id}/default - Set as default."""
        response = await async_client.post(f"/v1/payments/methods/{created_method['id']}/default/", headers=auth_headers)
        assert response.status_code == 200

    async def test_delete(self, async_client: AsyncClient, auth_headers, created_method):
        """DELETE /v1/payments/methods/{id} - Delete method."""
        response = await async_client.delete(f"/v1/payments/methods/{created_method['id']}/", headers=auth_headers)
        assert response.status_code == 200

        get_resp = await async_client.get(f"/v1/payments/methods/{created_method['id']}/", headers=auth_headers)
        assert get_resp.status_code == 404

    async def test_delete_not_found(self, async_client: AsyncClient, auth_headers):
        """DELETE /v1/payments/methods/{id} - Unknown ID returns 404."""
        response = await async_client.delete(f"/v1/payments/methods/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 404


@pytest.mark.api
class TestPaymentIntentEndpoints:

    async def test_create(self, async_client: AsyncClient, auth_headers):
        """POST /v1/payments/intents - Create a payment intent."""
        response = await async_client.post("/v1/payments/intents/", headers=auth_headers, json={"amount": 49.99})
        assert response.status_code == 201
        assert response.json()["data"]["amount"] == 49.99

    async def test_get_by_id(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/intents/{id} - Get an intent."""
        create = await async_client.post("/v1/payments/intents/", headers=auth_headers, json={"amount": 20.0})
        intent_id = create.json()["data"]["id"]

        response = await async_client.get(f"/v1/payments/intents/{intent_id}/", headers=auth_headers)
        assert response.status_code == 200

    async def test_get_by_id_not_found(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/intents/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/payments/intents/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 404

    async def test_list(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/intents - List intents."""
        await async_client.post("/v1/payments/intents/", headers=auth_headers, json={"amount": 15.0})
        response = await async_client.get("/v1/payments/intents/", headers=auth_headers)
        assert response.status_code == 200


@pytest.mark.api
class TestTransactionEndpoints:

    async def test_list(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/transactions - List own transactions."""
        response = await async_client.get("/v1/payments/transactions/", headers=auth_headers)
        assert response.status_code == 200

    async def test_get_not_found(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/transactions/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/payments/transactions/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 404

    async def test_admin_list_requires_admin(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/admin/transactions - Non-admin is forbidden."""
        response = await async_client.get("/v1/payments/admin/transactions/", headers=auth_headers)
        assert response.status_code == 403

    async def test_admin_list_as_admin(self, async_client: AsyncClient, admin_headers):
        """GET /v1/payments/admin/transactions - Admin can list all transactions."""
        response = await async_client.get("/v1/payments/admin/transactions/", headers=admin_headers)
        assert response.status_code == 200


@pytest.mark.api
class TestRefundEndpoints:

    async def test_list(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/refunds - List own refunds."""
        response = await async_client.get("/v1/payments/refunds/", headers=auth_headers)
        assert response.status_code == 200


@pytest.mark.api
class TestFailureHandlingEndpoints:

    async def test_status_not_found(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/failures/{id}/status - Unknown intent returns 404."""
        response = await async_client.get(f"/v1/payments/failures/{uuid4()}/status/", headers=auth_headers)
        assert response.status_code == 404

    async def test_retry_not_found(self, async_client: AsyncClient, auth_headers):
        """POST /v1/payments/failures/{id}/retry - Unknown intent."""
        response = await async_client.post(f"/v1/payments/failures/{uuid4()}/retry/", headers=auth_headers)
        assert response.status_code in [400, 404]

    async def test_list(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/failures - List failed payments."""
        response = await async_client.get("/v1/payments/failures/", headers=auth_headers)
        assert response.status_code == 200
