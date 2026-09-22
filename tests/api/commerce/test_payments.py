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


@pytest.fixture
async def succeeded_intent(async_client: AsyncClient, auth_headers, created_method):
    """A real, captured Stripe PaymentIntent - refund/confirm need one that actually succeeded."""
    response = await async_client.post("/v1/payments/process/", headers=auth_headers, params={
        "amount": 25.0, "payment_method_id": created_method["id"]
    })
    assert response.status_code == 200, response.text
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

    async def test_patch(self, async_client: AsyncClient, auth_headers, created_method):
        """PATCH /v1/payments/methods/{id} - Update a method."""
        response = await async_client.patch(f"/v1/payments/methods/{created_method['id']}/",
            headers=auth_headers, json={"is_default": True})
        assert response.status_code == 200
        assert response.json()["data"]["is_default"] is True

    async def test_patch_not_found(self, async_client: AsyncClient, auth_headers):
        """PATCH /v1/payments/methods/{id} - Unknown ID returns 404."""
        response = await async_client.patch(f"/v1/payments/methods/{uuid4()}/",
            headers=auth_headers, json={"is_default": True})
        assert response.status_code == 404

    async def test_set_default_not_found(self, async_client: AsyncClient, auth_headers):
        """POST /v1/payments/methods/{id}/default - Unknown ID returns 404."""
        response = await async_client.post(f"/v1/payments/methods/{uuid4()}/default/", headers=auth_headers)
        assert response.status_code == 404

    async def test_process_payment(self, async_client: AsyncClient, auth_headers, created_method):
        """POST /v1/payments/process - Process a payment against a real payment method."""
        response = await async_client.post("/v1/payments/process/", headers=auth_headers, params={
            "amount": 25.0, "payment_method_id": created_method["id"]
        })
        assert response.status_code == 200

    async def test_list_unauthenticated(self, async_client: AsyncClient):
        response = await async_client.get("/v1/payments/methods/")
        assert response.status_code == 401

    async def test_create_unauthenticated(self, async_client: AsyncClient):
        response = await async_client.post("/v1/payments/methods/", json={"type": "card"})
        assert response.status_code == 401

    async def test_list_with_search(self, async_client: AsyncClient, auth_headers, created_method):
        response = await async_client.get("/v1/payments/methods/?search=4242", headers=auth_headers)
        assert response.status_code == 200


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

    async def test_create_requires_admin(self, async_client: AsyncClient, auth_headers, succeeded_intent):
        response = await async_client.post("/v1/payments/refunds/", headers=auth_headers, json={
            "payment_intent_id": succeeded_intent["payment_intent_id"]
        })
        assert response.status_code == 403

    async def test_create_and_get(self, async_client: AsyncClient, admin_headers, auth_headers, succeeded_intent):
        created = await async_client.post("/v1/payments/refunds/", headers=admin_headers, json={
            "payment_intent_id": succeeded_intent["payment_intent_id"], "amount": 10.0
        })
        assert created.status_code == 201, created.text
        refund_id = created.json()["data"]["id"]

        response = await async_client.get(f"/v1/payments/refunds/{refund_id}/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["id"] == refund_id

    async def test_create_for_unknown_intent_returns_404(self, async_client: AsyncClient, admin_headers):
        response = await async_client.post("/v1/payments/refunds/", headers=admin_headers, json={
            "payment_intent_id": str(uuid4())
        })
        assert response.status_code == 404

    async def test_get_not_found(self, async_client: AsyncClient, auth_headers):
        response = await async_client.get(f"/v1/payments/refunds/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 404


@pytest.mark.api
class TestConfirmIntent:

    async def test_confirm_already_succeeded_intent(self, async_client: AsyncClient, auth_headers, succeeded_intent):
        response = await async_client.post(
            f"/v1/payments/intents/{succeeded_intent['payment_intent_id']}/confirm/",
            headers=auth_headers, params={"payment_method_id": fresh_stripe_payment_method_id()}
        )
        assert response.status_code in (200, 400)

    async def test_confirm_unknown_intent_returns_404(self, async_client: AsyncClient, auth_headers):
        response = await async_client.post(
            f"/v1/payments/intents/{uuid4()}/confirm/",
            headers=auth_headers, params={"payment_method_id": fresh_stripe_payment_method_id()}
        )
        assert response.status_code == 404


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
