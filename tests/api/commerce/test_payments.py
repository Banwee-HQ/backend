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

if not stripe.api_key.startswith("sk_test_") or "placeholder" in stripe.api_key:
    pytest.skip("Stripe integration tests require a real STRIPE_SECRET_KEY", allow_module_level=True)


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


@pytest.fixture
async def other_user(db_session):
    """A second, independent user - for non-owner/cross-account access tests.
    Defined locally (not in conftest.py) per this module's constraints."""
    from uuid import uuid4 as _uuid4
    from models.accounts.user import User, UserRole
    from core.utils.encryption import PasswordManager
    from core.utils.uuid_utils import uuid7
    user = User(
        id=uuid7(), email=f"other_{_uuid4().hex[:8]}@example.com",
        hashed_password=PasswordManager().hash_password("OtherPassword123!"),
        firstname="Other", lastname="User", phone="+1234567892",
        role=UserRole.CUSTOMER, account_status="active", verification_status="verified",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def other_auth_headers(async_client: AsyncClient, other_user):
    response = await async_client.post("/v1/auth/login/", json={
        "email": other_user.email, "password": "OtherPassword123!"
    })
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


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


# --------------------------------------------------------------------------- overview() - the optional service.overview() hook and its fallback branches. PaymentService has no `overview` method today, so hasattr() is always False in normal operation; monkeypatch is used here (not to mock Stripe or the DB, just to exercise this API-layer optional-hook branch) to add/remove that attribute for the duration of a single test. ---------------------------------------------------------------------------

@pytest.mark.api
class TestOverviewBranches:

    async def test_uses_overview_hook_when_present(self, async_client: AsyncClient, auth_headers, monkeypatch):
        from services.commerce.payments import PaymentService

        async def fake_overview(self, user_id):
            return {"total_spent": 42}
        monkeypatch.setattr(PaymentService, "overview", fake_overview, raising=False)

        response = await async_client.get("/v1/payments/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"] == {"total_spent": 42}

    async def test_overview_hook_failure_falls_back_to_empty_dict(self, async_client: AsyncClient, auth_headers, monkeypatch):
        from services.commerce.payments import PaymentService

        async def broken_overview(self, user_id):
            raise RuntimeError("boom")
        monkeypatch.setattr(PaymentService, "overview", broken_overview, raising=False)

        response = await async_client.get("/v1/payments/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"] == {}

    async def test_outer_failure_returns_500(self, async_client: AsyncClient, auth_headers, monkeypatch):
        import api.commerce.payments as payments_api

        original_success = payments_api.Response.success

        def broken_success(*args, **kwargs):
            raise RuntimeError("response construction failed")
        monkeypatch.setattr(payments_api.Response, "success", staticmethod(broken_success))

        response = await async_client.get("/v1/payments/", headers=auth_headers)
        assert response.status_code == 500
        monkeypatch.setattr(payments_api.Response, "success", staticmethod(original_success))


# --------------------------------------------------------------------------- create_method - Stripe-error and conflict branches ---------------------------------------------------------------------------

@pytest.mark.api
class TestCreateMethodErrors:

    async def test_declined_card_returns_400(self, async_client: AsyncClient, auth_headers):
        declining_pm_id = stripe.PaymentMethod.create(type="card", card={"token": "tok_chargeDeclined"}).id
        response = await async_client.post("/v1/payments/methods/", headers=auth_headers, json={
            "type": "card", "stripe_payment_method_id": declining_pm_id,
        })
        assert response.status_code == 400

    async def test_same_stripe_id_for_different_account_is_conflict(self, async_client: AsyncClient, auth_headers, other_auth_headers, created_method):
        response = await async_client.post("/v1/payments/methods/", headers=other_auth_headers, json={
            "type": "card", "stripe_payment_method_id": created_method["stripe_payment_method_id"],
        })
        assert response.status_code == 409


# --------------------------------------------------------------------------- Non-owner access - a user must never be able to read another user's payment records via a raw id, even when it definitely exists. ---------------------------------------------------------------------------

@pytest.mark.api
class TestNonOwnerAccessIsDenied:

    async def test_cannot_get_another_users_payment_method(self, async_client: AsyncClient, other_auth_headers, created_method):
        response = await async_client.get(f"/v1/payments/methods/{created_method['id']}/", headers=other_auth_headers)
        assert response.status_code == 404

    async def test_cannot_patch_another_users_payment_method(self, async_client: AsyncClient, other_auth_headers, created_method):
        response = await async_client.patch(
            f"/v1/payments/methods/{created_method['id']}/", headers=other_auth_headers, json={"is_default": True},
        )
        assert response.status_code == 404

    async def test_cannot_delete_another_users_payment_method(self, async_client: AsyncClient, other_auth_headers, created_method):
        response = await async_client.delete(f"/v1/payments/methods/{created_method['id']}/", headers=other_auth_headers)
        assert response.status_code == 404

    async def test_cannot_set_default_on_another_users_payment_method(self, async_client: AsyncClient, other_auth_headers, created_method):
        response = await async_client.post(f"/v1/payments/methods/{created_method['id']}/default/", headers=other_auth_headers)
        assert response.status_code == 404

    async def test_cannot_get_another_users_intent(self, async_client: AsyncClient, auth_headers, other_auth_headers):
        create = await async_client.post("/v1/payments/intents/", headers=auth_headers, json={"amount": 10.0})
        intent_id = create.json()["data"]["id"]
        response = await async_client.get(f"/v1/payments/intents/{intent_id}/", headers=other_auth_headers)
        assert response.status_code == 404

    async def test_cannot_get_another_users_transaction(self, async_client: AsyncClient, auth_headers, other_auth_headers, succeeded_intent):
        txn_list = await async_client.get("/v1/payments/transactions/", headers=auth_headers)
        txn_id = txn_list.json()["data"][0]["id"]
        response = await async_client.get(f"/v1/payments/transactions/{txn_id}/", headers=other_auth_headers)
        assert response.status_code == 404

    async def test_cannot_get_another_users_refund(self, async_client: AsyncClient, admin_headers, other_auth_headers, succeeded_intent):
        created = await async_client.post("/v1/payments/refunds/", headers=admin_headers, json={
            "payment_intent_id": succeeded_intent["payment_intent_id"], "amount": 5.0,
        })
        assert created.status_code == 201, created.text
        refund_id = created.json()["data"]["id"]
        response = await async_client.get(f"/v1/payments/refunds/{refund_id}/", headers=other_auth_headers)
        assert response.status_code == 404


# --------------------------------------------------------------------------- create_intent - real Stripe rejection and a real FK violation ---------------------------------------------------------------------------

@pytest.mark.api
class TestCreateIntentErrors:

    async def test_negative_amount_is_rejected_by_stripe(self, async_client: AsyncClient, auth_headers):
        response = await async_client.post("/v1/payments/intents/", headers=auth_headers, json={"amount": -5.0})
        assert response.status_code == 400

    async def test_nonexistent_order_id_is_reported_as_500(self, async_client: AsyncClient, auth_headers):
        """order_id has a real FK constraint to commerce.orders; create_intent()
        doesn't pre-validate it, so a bogus id must still surface as a clean error
        rather than corrupting the request."""
        response = await async_client.post("/v1/payments/intents/", headers=auth_headers, json={
            "amount": 10.0, "order_id": str(uuid4()),
        })
        assert response.status_code == 500


# --------------------------------------------------------------------------- Transactions - malformed metadata must not crash the listing endpoints ---------------------------------------------------------------------------

@pytest.mark.api
class TestTransactionListingResilience:

    async def test_corrupted_metadata_crashes_cleanly_as_500(self, async_client: AsyncClient, auth_headers, db_session, test_user):
        import json as _json
        from uuid import uuid4 as _uuid4
        from decimal import Decimal
        from models.commerce.payments import Transaction
        from core.utils.uuid_utils import uuid7
        txn = Transaction(
            id=uuid7(), user_id=test_user.id, amount=Decimal("5.00"), currency="USD",
            status="succeeded", transaction_type="payment",
            transaction_metadata=_json.dumps({"payment_method_type": 12345}),  # not a string -> .replace() blows up
        )
        db_session.add(txn)
        await db_session.commit()

        response = await async_client.get("/v1/payments/transactions/", headers=auth_headers)
        assert response.status_code == 500

    async def test_admin_listing_corrupted_metadata_crashes_cleanly_as_500(self, async_client: AsyncClient, admin_headers, db_session, test_user):
        import json as _json
        from decimal import Decimal
        from models.commerce.payments import Transaction
        from core.utils.uuid_utils import uuid7
        txn = Transaction(
            id=uuid7(), user_id=test_user.id, amount=Decimal("5.00"), currency="USD",
            status="succeeded", transaction_type="payment",
            transaction_metadata=_json.dumps({"payment_method_type": 12345}),
        )
        db_session.add(txn)
        await db_session.commit()

        response = await async_client.get("/v1/payments/admin/transactions/", headers=admin_headers)
        assert response.status_code == 500


# --------------------------------------------------------------------------- Refunds - Stripe error and a malformed-record 500 ---------------------------------------------------------------------------

@pytest.mark.api
class TestRefundErrors:

    async def test_refund_amount_exceeding_charge_returns_400(self, async_client: AsyncClient, admin_headers, succeeded_intent):
        response = await async_client.post("/v1/payments/refunds/", headers=admin_headers, json={
            "payment_intent_id": succeeded_intent["payment_intent_id"], "amount": 999999.0,
        })
        assert response.status_code == 400

    async def test_missing_amount_breakdown_returns_500(self, async_client: AsyncClient, admin_headers, db_session, succeeded_intent):
        from models.commerce.payments import PaymentIntent
        from sqlalchemy import select
        result = await db_session.execute(
            select(PaymentIntent).where(PaymentIntent.id == succeeded_intent["payment_intent_id"])
        )
        intent = result.scalar_one()
        intent.amount_breakdown = None
        await db_session.commit()

        response = await async_client.post("/v1/payments/refunds/", headers=admin_headers, json={
            "payment_intent_id": succeeded_intent["payment_intent_id"],
        })
        assert response.status_code == 500


# --------------------------------------------------------------------------- process_payment - Stripe decline and non-existent payment method ---------------------------------------------------------------------------

@pytest.mark.api
class TestProcessPaymentErrors:

    async def test_unknown_payment_method_returns_404(self, async_client: AsyncClient, auth_headers):
        response = await async_client.post("/v1/payments/process/", headers=auth_headers, params={
            "amount": 5.0, "payment_method_id": str(uuid4()),
        })
        assert response.status_code == 404

    async def test_process_payment_requires_auth(self, async_client: AsyncClient):
        response = await async_client.post("/v1/payments/process/", params={
            "amount": 5.0, "payment_method_id": str(uuid4()),
        })
        assert response.status_code == 401


# --------------------------------------------------------------------------- Failure handling endpoints - malformed failure_reason must not crash the API with a raw ValueError. ---------------------------------------------------------------------------

@pytest.mark.api
class TestFailureHandlingErrors:

    @pytest.fixture
    async def corrupted_failed_intent(self, db_session, test_user):
        from models.commerce.payments import PaymentIntent
        from core.utils.uuid_utils import uuid7
        from datetime import datetime
        intent = PaymentIntent(
            id=uuid7(), stripe_payment_intent_id=f"pi_test_{uuid4().hex[:16]}", user_id=test_user.id,
            amount_breakdown={"total": 10.0, "currency": "USD"}, currency="USD", status="failed",
            failed_at=datetime.utcnow(), failure_reason="not_a_real_failure_reason",
        )
        db_session.add(intent)
        await db_session.commit()
        await db_session.refresh(intent)
        return intent

    async def test_status_with_corrupted_failure_reason_returns_500(self, async_client: AsyncClient, auth_headers, corrupted_failed_intent):
        """failure_status() has no try/except of its own - a raw ValueError from an
        invalid stored failure_reason must still be wrapped into a clean 500 by the
        API layer's own except Exception clause."""
        response = await async_client.get(
            f"/v1/payments/failures/{corrupted_failed_intent.id}/status/", headers=auth_headers,
        )
        assert response.status_code == 500

    async def test_retry_with_corrupted_failure_reason_returns_500(self, async_client: AsyncClient, auth_headers, corrupted_failed_intent):
        response = await async_client.post(
            f"/v1/payments/failures/{corrupted_failed_intent.id}/retry/", headers=auth_headers,
        )
        assert response.status_code == 500

    async def test_retry_with_unknown_new_payment_method_returns_404(self, async_client: AsyncClient, auth_headers, db_session, test_user):
        from models.commerce.payments import PaymentIntent, PaymentFailureReason
        from core.utils.uuid_utils import uuid7
        from datetime import datetime
        intent = PaymentIntent(
            id=uuid7(), stripe_payment_intent_id=f"pi_test_{uuid4().hex[:16]}", user_id=test_user.id,
            amount_breakdown={"total": 10.0, "currency": "USD"}, currency="USD", status="failed",
            failed_at=datetime.utcnow(), failure_reason=PaymentFailureReason.CARD_DECLINED.value,
            failure_metadata={"retry_count": 0},
        )
        db_session.add(intent)
        await db_session.commit()

        response = await async_client.post(
            f"/v1/payments/failures/{intent.id}/retry/", headers=auth_headers,
            params={"new_payment_method_id": str(uuid4())},
        )
        assert response.status_code == 404
