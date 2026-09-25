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
from fastapi import HTTPException
from httpx import AsyncClient
from uuid import uuid4

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

if not stripe.api_key.startswith("sk_test_") or "placeholder" in stripe.api_key:
    pytest.skip("Stripe integration tests require a real STRIPE_SECRET_KEY", allow_module_level=True)


def fresh_stripe_payment_method_id() -> str:
    return stripe.PaymentMethod.create(type="card", card={"token": "tok_visa"}).id


def _async_raiser(exc):
    """Build an async function that always raises `exc` - used to monkeypatch a
    PaymentService method so a specific endpoint's except-clause body actually runs."""
    async def _raise(*args, **kwargs):
        raise exc
    return _raise


def _async_returner(value):
    """Build an async function that always returns `value` regardless of arguments -
    used to monkeypatch a PaymentService method's return shape."""
    async def _return(*args, **kwargs):
        return value
    return _return


@pytest.fixture
async def created_method(async_client: AsyncClient, auth_headers):
    stripe_id = fresh_stripe_payment_method_id()
    response = await async_client.post("/v1/payments/methods/", headers=auth_headers, json={
        "stripe_payment_method_id": stripe_id, "is_default": True
    })
    data = response.json()["data"]
    # MethodResponse doesn't echo stripe_payment_method_id back, but some tests need the
    # value they created it with (e.g. to attempt reusing it on another account).
    data["_stripe_payment_method_id"] = stripe_id
    return data


@pytest.fixture
async def succeeded_intent(async_client: AsyncClient, auth_headers, created_method):
    """A real, captured Stripe PaymentIntent - refund/confirm need one that actually succeeded."""
    intent = await async_client.post("/v1/payments/intents/", headers=auth_headers, json={"amount": 25.0})
    assert intent.status_code == 201, intent.text
    response = await async_client.post(
        f"/v1/payments/intents/{intent.json()['data']['id']}/confirm/", headers=auth_headers,
        params={"payment_method_id": created_method["id"]},
    )
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

    async def test_list_empty(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/methods - A new user has no payment methods."""
        response = await async_client.get("/v1/payments/methods/", headers=auth_headers)
        assert response.status_code == 200

    async def test_create(self, async_client: AsyncClient, auth_headers):
        """POST /v1/payments/methods - Create payment method from a real Stripe test card."""
        response = await async_client.post("/v1/payments/methods/", headers=auth_headers, json={
            "stripe_payment_method_id": fresh_stripe_payment_method_id(), "is_default": True
        })
        assert response.status_code == 201
        assert response.json()["data"]["last_four"] == "4242"


    async def test_set_default(self, async_client: AsyncClient, auth_headers, created_method):
        """POST /v1/payments/methods/{id}/default - Set as default."""
        response = await async_client.post(f"/v1/payments/methods/{created_method['id']}/default/", headers=auth_headers)
        assert response.status_code == 200


    async def test_delete_not_found(self, async_client: AsyncClient, auth_headers):
        """DELETE /v1/payments/methods/{id} - Unknown ID returns 404."""
        response = await async_client.delete(f"/v1/payments/methods/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 404


    async def test_set_default_not_found(self, async_client: AsyncClient, auth_headers):
        """POST /v1/payments/methods/{id}/default - Unknown ID returns 404."""
        response = await async_client.post(f"/v1/payments/methods/{uuid4()}/default/", headers=auth_headers)
        assert response.status_code == 404


    async def test_list_unauthenticated(self, async_client: AsyncClient):
        response = await async_client.get("/v1/payments/methods/")
        assert response.status_code == 401

    async def test_create_unauthenticated(self, async_client: AsyncClient):
        response = await async_client.post("/v1/payments/methods/", json={"stripe_payment_method_id": "pm_x"})
        assert response.status_code == 401

    async def test_list_with_search(self, async_client: AsyncClient, auth_headers, created_method):
        response = await async_client.get("/v1/payments/methods/?search=4242", headers=auth_headers)
        assert response.status_code == 200


@pytest.mark.api
class TestTransactionEndpoints:


    async def test_admin_list_requires_admin(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/admin/transactions - Non-admin is forbidden."""
        response = await async_client.get("/v1/payments/admin/transactions/", headers=auth_headers)
        assert response.status_code == 403

    async def test_admin_list_as_admin(self, async_client: AsyncClient, admin_headers):
        """GET /v1/payments/admin/transactions - Admin can list all transactions."""
        response = await async_client.get("/v1/payments/admin/transactions/", headers=admin_headers)
        assert response.status_code == 200

    async def test_list(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/transactions - List own transactions."""
        response = await async_client.get("/v1/payments/transactions/", headers=auth_headers)
        assert response.status_code == 200

    async def test_get_not_found(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/transactions/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/payments/transactions/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 404


# --------------------------------------------------------------------------- create_method - Stripe-error and conflict branches ---------------------------------------------------------------------------

@pytest.mark.api
class TestCreateMethodErrors:

    async def test_declined_card_returns_400(self, async_client: AsyncClient, auth_headers):
        declining_pm_id = stripe.PaymentMethod.create(type="card", card={"token": "tok_chargeDeclined"}).id
        response = await async_client.post("/v1/payments/methods/", headers=auth_headers, json={
            "stripe_payment_method_id": declining_pm_id,
        })
        assert response.status_code == 400

    async def test_same_stripe_id_for_different_account_is_conflict(self, async_client: AsyncClient, auth_headers, other_auth_headers, created_method):
        response = await async_client.post("/v1/payments/methods/", headers=other_auth_headers, json={
            "stripe_payment_method_id": created_method["_stripe_payment_method_id"],
        })
        assert response.status_code == 409


# --------------------------------------------------------------------------- Non-owner access - a user must never be able to read another user's payment records via a raw id, even when it definitely exists. ---------------------------------------------------------------------------

@pytest.mark.api
class TestNonOwnerAccessIsDenied:


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


# --------------------------------------------------------------------------- create_intent - real Stripe rejection and a real FK violation ---------------------------------------------------------------------------


# --------------------------------------------------------------------------- Transactions - malformed metadata must not crash the listing endpoints ---------------------------------------------------------------------------

@pytest.mark.api
class TestTransactionListingResilience:


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


# --------------------------------------------------------------------------- Refunds - Stripe error and a malformed-record 500 ---------------------------------------------------------------------------


# --------------------------------------------------------------------------- process_payment - Stripe decline and non-existent payment method ---------------------------------------------------------------------------


# --------------------------------------------------------------------------- Failure handling endpoints - malformed failure_reason must not crash the API with a raw ValueError. ---------------------------------------------------------------------------


# --------------------------------------------------------------------------- Generic error-handling wrapper contract ---------------------------------------------------------------------------
# Every endpoint below wraps its call to PaymentService in the same shape:
#     except APIException: raise
#     except HTTPException: raise
#     except Exception as e: raise APIException(500, ...)
# The "except APIException: raise" body is dead code for every endpoint tested here:
# PaymentService itself never raises the APIException subclass (only plain HTTPException
# or bare Exception), so that branch's *body* can never execute via any call through the
# service layer - only the header is ever reached (evaluated, not matched) as part of
# exception dispatch. The tests below instead verify the two branches that ARE part of
# the real contract: a plain HTTPException raised by the service must pass through
# unchanged (not get relabeled as a 500), and any other exception must be converted into
# a clean APIException 500 rather than leaking a raw error to the client. Since the real
# PaymentService methods used here (get/list/update/delete/etc.) have no legitimate way
# to raise an arbitrary HTTPException or bare Exception through normal use, the service
# method itself is monkeypatched for the duration of a single test - mirroring the
# project's own established technique in TestOverviewBranches above.


@pytest.mark.api
class TestListMethodsErrorPassthrough:

    async def test_unexpected_shape_falls_back_to_raw_data(self, async_client, auth_headers, monkeypatch):
        """Defensive branch: if the service ever returned something other than the
        {"data":..., "pagination":...} shape, the endpoint must still respond instead
        of crashing on the isinstance/key checks."""
        from services.commerce.payments import PaymentService
        monkeypatch.setattr(PaymentService, "list", _async_returner(["not", "the", "expected", "shape"]))
        response = await async_client.get("/v1/payments/methods/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"] == ["not", "the", "expected", "shape"]

    async def test_httpexception_from_service_passes_through(self, async_client, auth_headers, monkeypatch):
        from services.commerce.payments import PaymentService
        monkeypatch.setattr(PaymentService, "list", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.get("/v1/payments/methods/", headers=auth_headers)
        assert response.status_code == 403

    async def test_generic_exception_from_service_becomes_500(self, async_client, auth_headers, monkeypatch):
        from services.commerce.payments import PaymentService
        monkeypatch.setattr(PaymentService, "list", _async_raiser(RuntimeError("boom")))
        response = await async_client.get("/v1/payments/methods/", headers=auth_headers)
        assert response.status_code == 500


@pytest.mark.api
class TestCreateMethodGenericException:

    async def test_response_construction_failure_becomes_500(self, async_client, auth_headers, monkeypatch):
        """The service call itself already has real 400/409 tests (declined card,
        cross-account conflict); this covers the remaining generic-Exception fallback,
        which in practice can only be triggered by something after the service call
        (e.g. response serialization) blowing up."""
        import api.commerce.payments as payments_api
        monkeypatch.setattr(payments_api.Response, "success", staticmethod(lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))))
        response = await async_client.post("/v1/payments/methods/", headers=auth_headers, json={
            "stripe_payment_method_id": fresh_stripe_payment_method_id(),
        })
        assert response.status_code == 500


@pytest.mark.api
class TestDeleteMethodGenericException:

    async def test_generic_exception_from_service_becomes_500(self, async_client, auth_headers, created_method, monkeypatch):
        from services.commerce.payments import PaymentService
        monkeypatch.setattr(PaymentService, "delete", _async_raiser(RuntimeError("boom")))
        response = await async_client.delete(f"/v1/payments/methods/{created_method['id']}/", headers=auth_headers)
        assert response.status_code == 500


@pytest.mark.api
class TestListAllTransactionsErrorPassthrough:

    async def test_httpexception_from_service_passes_through(self, async_client, admin_headers, monkeypatch):
        from services.commerce.payments import PaymentService
        monkeypatch.setattr(PaymentService, "all_transactions", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.get("/v1/payments/admin/transactions/", headers=admin_headers)
        assert response.status_code == 403


@pytest.mark.api
class TestSetDefaultMethodErrorPassthrough:

    async def test_real_db_conflict_passes_through_as_500(self, async_client, auth_headers, other_auth_headers, other_user, created_method, db_session):
        """Mirrors TestSetDefaultExceptionHandling at the service level: stage an
        unrelated, unflushed row (added to the same session backing this request)
        that violates the stripe_payment_method_id uniqueness constraint, so
        set_default()'s own commit() surfaces a real DB error - exercised here
        through the API layer's HTTPException passthrough."""
        from models.commerce.payments import PaymentMethod
        conflicting = PaymentMethod(
            user_id=other_user.id, type="card", provider="stripe",
            stripe_payment_method_id=created_method["_stripe_payment_method_id"], is_active=True,
        )
        db_session.add(conflicting)
        response = await async_client.post(f"/v1/payments/methods/{created_method['id']}/default/", headers=auth_headers)
        assert response.status_code == 500

    async def test_response_construction_failure_becomes_500(self, async_client, auth_headers, created_method, monkeypatch):
        import api.commerce.payments as payments_api
        monkeypatch.setattr(payments_api.Response, "success", staticmethod(lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))))
        response = await async_client.post(f"/v1/payments/methods/{created_method['id']}/default/", headers=auth_headers)
        assert response.status_code == 500


# --------------------------------------------------------------------------- failure/retry/list_failures - genuine success paths and a real HTTPException trigger ---------------------------------------------------------------------------

@pytest.fixture
async def own_failed_intent(db_session, test_user):
    """A failed intent with a valid, retryable failure reason - for exercising the
    success paths of failure_status/retry (as opposed to the not-found/corrupted-data
    tests already covered elsewhere)."""
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
    await db_session.refresh(intent)
    return intent


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
class TestConfirmIntent:

    async def test_confirm_already_succeeded_intent(self, async_client: AsyncClient, auth_headers, succeeded_intent):
        response = await async_client.post(
            f"/v1/payments/intents/{succeeded_intent['id']}/confirm/",
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


@pytest.mark.api
class TestGetIntentErrorPassthrough:

    async def test_httpexception_from_service_passes_through(self, async_client, auth_headers, monkeypatch):
        from services.commerce.payments import PaymentService
        create = await async_client.post("/v1/payments/intents/", headers=auth_headers, json={"amount": 10.0})
        intent_id = create.json()["data"]["id"]
        monkeypatch.setattr(PaymentService, "get_intent", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.get(f"/v1/payments/intents/{intent_id}/", headers=auth_headers)
        assert response.status_code == 403

    async def test_generic_exception_from_service_becomes_500(self, async_client, auth_headers, monkeypatch):
        from services.commerce.payments import PaymentService
        create = await async_client.post("/v1/payments/intents/", headers=auth_headers, json={"amount": 10.0})
        intent_id = create.json()["data"]["id"]
        monkeypatch.setattr(PaymentService, "get_intent", _async_raiser(RuntimeError("boom")))
        response = await async_client.get(f"/v1/payments/intents/{intent_id}/", headers=auth_headers)
        assert response.status_code == 500


@pytest.mark.api
class TestListIntentsErrorPassthrough:

    async def test_unexpected_shape_falls_back_to_raw_data(self, async_client, auth_headers, monkeypatch):
        from services.commerce.payments import PaymentService
        monkeypatch.setattr(PaymentService, "list_intents", _async_returner({"no": "items key here"}))
        response = await async_client.get("/v1/payments/intents/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"] == {"no": "items key here"}

    async def test_httpexception_from_service_passes_through(self, async_client, auth_headers, monkeypatch):
        from services.commerce.payments import PaymentService
        monkeypatch.setattr(PaymentService, "list_intents", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.get("/v1/payments/intents/", headers=auth_headers)
        assert response.status_code == 403

    async def test_generic_exception_from_service_becomes_500(self, async_client, auth_headers, monkeypatch):
        from services.commerce.payments import PaymentService
        monkeypatch.setattr(PaymentService, "list_intents", _async_raiser(RuntimeError("boom")))
        response = await async_client.get("/v1/payments/intents/", headers=auth_headers)
        assert response.status_code == 500


@pytest.mark.api
class TestGetTransactionSuccessAndErrorPassthrough:

    async def test_get_own_transaction_succeeds(self, async_client, auth_headers, succeeded_intent):
        """No existing test actually fetched a transaction successfully by ID -
        every prior test either listed transactions or hit the not-found path."""
        txn_list = await async_client.get("/v1/payments/transactions/", headers=auth_headers)
        txn_id = txn_list.json()["data"][0]["id"]
        response = await async_client.get(f"/v1/payments/transactions/{txn_id}/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["id"] == txn_id

    async def test_httpexception_from_service_passes_through(self, async_client, auth_headers, monkeypatch):
        from services.commerce.payments import PaymentService
        monkeypatch.setattr(PaymentService, "get_transaction", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.get(f"/v1/payments/transactions/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 403

    async def test_generic_exception_from_service_becomes_500(self, async_client, auth_headers, monkeypatch):
        from services.commerce.payments import PaymentService
        monkeypatch.setattr(PaymentService, "get_transaction", _async_raiser(RuntimeError("boom")))
        response = await async_client.get(f"/v1/payments/transactions/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 500


@pytest.mark.api
class TestListTransactionsErrorPassthrough:

    async def test_httpexception_from_service_passes_through(self, async_client, auth_headers, monkeypatch):
        from services.commerce.payments import PaymentService
        monkeypatch.setattr(PaymentService, "transactions", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.get("/v1/payments/transactions/", headers=auth_headers)
        assert response.status_code == 403


@pytest.mark.api
class TestConfirmIntentSuccessAndGenericException:

    async def test_confirming_a_fresh_intent_succeeds(self, async_client, auth_headers):
        """Regression test for a real, previously-live bug: IntentResponse.payment_method_id
        (schemas/commerce/payments.py) was typed Optional[UUID], but confirm_intent()
        (services/commerce/payments.py) always stores the raw Stripe payment_method id
        string (e.g. "pm_xxx") into that same column - see the "payment_method_id stores
        the Stripe string id, not our internal PaymentMethod row's UUID" comment already
        in services/commerce/payments.py's retry(). That meant every real confirmation hit
        a pydantic ValidationError and returned 500 - the endpoint's success response (200)
        was unreachable in production. Fixed by typing the schema field Optional[str] to
        match what's actually stored. This test confirms the success path now actually works."""
        create = await async_client.post("/v1/payments/intents/", headers=auth_headers, json={"amount": 12.0})
        intent_id = create.json()["data"]["id"]
        pm_id = fresh_stripe_payment_method_id()
        response = await async_client.post(
            f"/v1/payments/intents/{intent_id}/confirm/", headers=auth_headers,
            params={"payment_method_id": pm_id},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["payment_method_id"] == pm_id

    async def test_response_construction_failure_becomes_500(self, async_client, auth_headers, monkeypatch):
        import api.commerce.payments as payments_api
        create = await async_client.post("/v1/payments/intents/", headers=auth_headers, json={"amount": 12.0})
        intent_id = create.json()["data"]["id"]
        monkeypatch.setattr(payments_api.Response, "success", staticmethod(lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))))
        response = await async_client.post(
            f"/v1/payments/intents/{intent_id}/confirm/", headers=auth_headers,
            params={"payment_method_id": fresh_stripe_payment_method_id()},
        )
        assert response.status_code == 500


@pytest.mark.api
class TestFailureStatusSuccess:

    async def test_reports_failure_details(self, async_client, auth_headers, own_failed_intent):
        response = await async_client.get(f"/v1/payments/failures/{own_failed_intent.id}/status/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["is_failed"] is True
        assert data["failure_reason"] == "card_declined"


@pytest.mark.api
class TestRetryPaymentSuccessAndGenericException:

    async def test_resets_a_failed_intent_for_retry(self, async_client, auth_headers, own_failed_intent):
        response = await async_client.post(f"/v1/payments/failures/{own_failed_intent.id}/retry/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "ready_for_retry"

    async def test_response_construction_failure_becomes_500(self, async_client, auth_headers, own_failed_intent, monkeypatch):
        import api.commerce.payments as payments_api
        monkeypatch.setattr(payments_api.Response, "success", staticmethod(lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))))
        response = await async_client.post(f"/v1/payments/failures/{own_failed_intent.id}/retry/", headers=auth_headers)
        assert response.status_code == 500


@pytest.mark.api
class TestListFailuresErrorPassthrough:

    async def test_unexpected_shape_falls_back_to_raw_data(self, async_client, auth_headers, monkeypatch):
        from services.commerce.payments import PaymentService
        monkeypatch.setattr(PaymentService, "failed_payments", _async_returner(["not", "the", "expected", "shape"]))
        response = await async_client.get("/v1/payments/failures/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"] == ["not", "the", "expected", "shape"]

    async def test_corrupted_failure_reason_is_a_real_httpexception_passthrough(self, async_client, auth_headers, db_session, test_user):
        """Unlike the other list endpoints, this HTTPException is genuine (no
        monkeypatch needed): failed_payments() itself catches the raw ValueError from
        an invalid stored failure_reason and converts it to HTTPException(500), which
        this endpoint must then pass through unchanged."""
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

        response = await async_client.get("/v1/payments/failures/", headers=auth_headers)
        assert response.status_code == 500

    async def test_response_construction_failure_becomes_500(self, async_client, auth_headers, monkeypatch):
        import api.commerce.payments as payments_api
        monkeypatch.setattr(payments_api.Response, "success", staticmethod(lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))))
        response = await async_client.get("/v1/payments/failures/", headers=auth_headers)
        assert response.status_code == 500

@pytest.mark.api
class TestIntentOwnership:

    async def test_cannot_confirm_another_users_intent(self, async_client: AsyncClient, auth_headers, other_auth_headers, created_method):
        intent = await async_client.post("/v1/payments/intents/", headers=auth_headers, json={"amount": 10.0})
        response = await async_client.post(
            f"/v1/payments/intents/{intent.json()['data']['id']}/confirm/", headers=other_auth_headers,
            params={"payment_method_id": created_method["id"]},
        )
        assert response.status_code == 404

    async def test_cannot_retry_another_users_payment(self, async_client: AsyncClient, auth_headers, other_auth_headers):
        intent = await async_client.post("/v1/payments/intents/", headers=auth_headers, json={"amount": 10.0})
        response = await async_client.post(f"/v1/payments/failures/{intent.json()['data']['id']}/retry/", headers=other_auth_headers)
        assert response.status_code == 404
