"""Tests for services/commerce/webhooks.py - WebhookService and verify_stripe_webhook_request.

Regression coverage for two bugs that made every order-linked Stripe webhook
crash before it could commit anything:
- transaction.transaction_details_metadata doesn't exist on Transaction (the
  real column is transaction_metadata, a JSON-serialized string) - reading it
  via **unpacking raised AttributeError on every payment_intent.succeeded/
  payment_intent.payment_failed event.
- order.version += 1 assumed an optimistic-locking column that Order doesn't
  have at all - AttributeError on every webhook that found a matching order.
Both bugs meant a webhook that matched a real transaction+order always
500'd before its DB writes landed, so orders never actually got confirmed
or marked failed/cancelled by webhook in production.
"""

import json
import pytest
from uuid import uuid4
from unittest.mock import MagicMock

import stripe

from services.commerce.webhooks import WebhookService, WebhookSecurityError, verify_stripe_webhook_request
from services.accounts.auth import AuthService
from models.accounts.user import User, UserRole
from models.commerce.orders import Order, OrderStatus, PaymentStatus
from models.commerce.payments import Transaction, PaymentIntent


async def make_user(db_session) -> User:
    auth = AuthService(db_session)
    user = User(
        id=uuid4(),
        email=f"webhook_test_{uuid4().hex[:8]}@example.com",
        firstname="Test",
        lastname="User",
        hashed_password=auth.get_password_hash("Password123!"),
        role=UserRole.CUSTOMER,
        account_status="active",
        verification_status="verified",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def make_order(db_session, user_id, **overrides) -> Order:
    fields = {
        "id": uuid4(),
        "order_number": f"ORD-{uuid4().hex[:10].upper()}",
        "user_id": user_id,
        "subtotal": 100.0,
        "total_amount": 100.0,
        "billing_address": {"street": "1 St", "city": "City", "country": "US"},
        "shipping_address": {"street": "1 St", "city": "City", "country": "US"},
    }
    fields.update(overrides)
    order = Order(**fields)
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


async def make_transaction(db_session, user_id, order_id=None, stripe_payment_intent_id=None,
                            existing_metadata=None, **overrides) -> Transaction:
    fields = {
        "id": uuid4(),
        "user_id": user_id,
        "order_id": order_id,
        "stripe_payment_intent_id": stripe_payment_intent_id or f"pi_{uuid4().hex[:16]}",
        "amount": 100.0,
        "status": "pending",
        "transaction_type": "payment",
        "transaction_metadata": json.dumps(existing_metadata) if existing_metadata is not None else None,
    }
    fields.update(overrides)
    transaction = Transaction(**fields)
    db_session.add(transaction)
    await db_session.commit()
    await db_session.refresh(transaction)
    return transaction


class TestVerifyStripeWebhookRequest:

    async def test_valid_signature_returns_verified_event(self, db_session, mocker):
        fake_event = {"id": "evt_1", "type": "payment_intent.succeeded", "created": 12345,
                      "data": {"object": {}}}
        mocker.patch("stripe.Webhook.construct_event", return_value=fake_event)

        result = await verify_stripe_webhook_request(
            request=MagicMock(), db=db_session, signature_header="sig", payload=b"{}"
        )
        assert result["verified"] is True
        assert result["security_metadata"]["event_id"] == "evt_1"

    async def test_invalid_payload_raises_security_error(self, db_session, mocker):
        mocker.patch("stripe.Webhook.construct_event", side_effect=ValueError("bad payload"))
        with pytest.raises(WebhookSecurityError):
            await verify_stripe_webhook_request(
                request=MagicMock(), db=db_session, signature_header="sig", payload=b"not json"
            )

    async def test_bad_signature_raises_security_error(self, db_session, mocker):
        mocker.patch(
            "stripe.Webhook.construct_event",
            side_effect=stripe.error.SignatureVerificationError("bad sig", "sig_header"),
        )
        with pytest.raises(WebhookSecurityError):
            await verify_stripe_webhook_request(
                request=MagicMock(), db=db_session, signature_header="sig", payload=b"{}"
            )


class TestHandlePaymentSucceeded:

    async def test_confirms_transaction_and_order(self, db_session):
        user = await make_user(db_session)
        order = await make_order(db_session, user.id)
        transaction = await make_transaction(db_session, user.id, order_id=order.id)
        service = WebhookService(db_session)

        result = await service._handle_payment_succeeded({
            "id": transaction.stripe_payment_intent_id, "charges": {"data": []}
        })

        assert result["action"] == "payment_confirmed"
        await db_session.refresh(transaction)
        await db_session.refresh(order)
        assert transaction.status == "succeeded"
        assert order.order_status == OrderStatus.CONFIRMED
        assert order.confirmed_at is not None

    async def test_merges_into_existing_metadata_without_clobbering_it(self, db_session):
        user = await make_user(db_session)
        transaction = await make_transaction(db_session, user.id, existing_metadata={"original": "value"})
        service = WebhookService(db_session)

        await service._handle_payment_succeeded({"id": transaction.stripe_payment_intent_id})

        await db_session.refresh(transaction)
        metadata = json.loads(transaction.transaction_metadata)
        assert metadata["original"] == "value"
        assert "webhook_confirmed_at" in metadata

    async def test_unmatched_payment_intent_does_not_raise(self, db_session):
        service = WebhookService(db_session)
        result = await service._handle_payment_succeeded({"id": "pi_does_not_exist"})
        assert result["warning"] == "transaction_not_found"


class TestHandlePaymentFailed:

    async def test_marks_transaction_and_order_failed(self, db_session):
        user = await make_user(db_session)
        order = await make_order(db_session, user.id)
        transaction = await make_transaction(db_session, user.id, order_id=order.id)
        service = WebhookService(db_session)

        result = await service._handle_payment_failed({
            "id": transaction.stripe_payment_intent_id,
            "last_payment_error": {"message": "Card declined"},
        })

        assert result["action"] == "payment_failed"
        await db_session.refresh(transaction)
        await db_session.refresh(order)
        assert transaction.status == "failed"
        assert transaction.failure_reason == "Card declined"
        assert order.order_status == OrderStatus.CANCELLED
        assert order.payment_status == PaymentStatus.FAILED

    async def test_unmatched_payment_intent_does_not_raise(self, db_session):
        service = WebhookService(db_session)
        result = await service._handle_payment_failed({"id": "pi_does_not_exist"})
        assert result["warning"] == "transaction_not_found"


class TestHandlePaymentCanceled:

    async def test_marks_transaction_and_order_cancelled(self, db_session):
        user = await make_user(db_session)
        order = await make_order(db_session, user.id)
        transaction = await make_transaction(db_session, user.id, order_id=order.id)
        service = WebhookService(db_session)

        result = await service._handle_payment_canceled({"id": transaction.stripe_payment_intent_id})

        assert result["action"] == "payment_cancelled"
        await db_session.refresh(transaction)
        await db_session.refresh(order)
        assert transaction.status == "cancelled"
        assert order.order_status == OrderStatus.CANCELLED
        assert order.cancelled_at is not None

    async def test_unmatched_payment_intent_does_not_raise(self, db_session):
        service = WebhookService(db_session)
        result = await service._handle_payment_canceled({"id": "pi_does_not_exist"})
        assert result["warning"] == "transaction_not_found"


class TestProcessWebhookEventDispatch:

    async def test_dispatches_to_payment_succeeded(self, db_session):
        user = await make_user(db_session)
        transaction = await make_transaction(db_session, user.id)
        service = WebhookService(db_session)

        result = await service._process_webhook_event({
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": transaction.stripe_payment_intent_id}},
        })
        assert result["action"] == "payment_confirmed"

    async def test_unhandled_event_type_is_ignored(self, db_session):
        service = WebhookService(db_session)
        result = await service._process_webhook_event({
            "type": "customer.created",
            "data": {"object": {}},
        })
        assert result == {"status": "ignored", "reason": "unhandled_event_type"}

    async def test_charge_refunded_is_handled(self, db_session):
        service = WebhookService(db_session)
        result = await service._process_webhook_event({
            "type": "charge.refunded",
            "data": {"object": {"id": "ch_123"}},
        })
        assert result == {"action": "refund_processed", "charge_id": "ch_123"}
