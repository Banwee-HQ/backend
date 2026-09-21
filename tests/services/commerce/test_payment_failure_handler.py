"""Tests for services/commerce/payment_failure_handler.py - PaymentFailureHandler.

Regression coverage for a method-name mismatch: this class only ever defined
handle_payment_failure, but both real callers (services/commerce/payments.py
and services/commerce/webhooks.py) call failure_handler.handle_failure(...) -
an AttributeError that was silently swallowed by a broad except in both
callers, so no comprehensive failure guidance (or payment_intent_metadata
update) ever actually happened on a failed payment. Renamed the method to
handle_failure to match every real call site.
"""

import pytest
from uuid import uuid4

from services.accounts.auth import AuthService
from services.commerce.payment_failure_handler import PaymentFailureHandler
from models.accounts.user import User, UserRole
from models.commerce.payments import PaymentIntent, PaymentFailureReason


async def make_user(db_session) -> User:
    auth = AuthService(db_session)
    user = User(
        id=uuid4(),
        email=f"failure_test_{uuid4().hex[:8]}@example.com",
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


async def make_payment_intent(db_session, user_id, **overrides) -> PaymentIntent:
    fields = {
        "id": uuid4(),
        "stripe_payment_intent_id": f"pi_{uuid4().hex[:16]}",
        "user_id": user_id,
        "amount_breakdown": {"subtotal": 100.0},
        "status": "requires_payment_method",
    }
    fields.update(overrides)
    intent = PaymentIntent(**fields)
    db_session.add(intent)
    await db_session.commit()
    await db_session.refresh(intent)
    return intent


class TestHandleFailure:

    async def test_unknown_payment_intent_returns_not_found(self, db_session):
        handler = PaymentFailureHandler(db_session)
        result = await handler.handle_failure(payment_intent_id=uuid4())
        assert result["status"] == "not_found"

    async def test_marks_intent_failed_with_metadata(self, db_session):
        user = await make_user(db_session)
        intent = await make_payment_intent(db_session, user.id)
        handler = PaymentFailureHandler(db_session)

        result = await handler.handle_failure(
            payment_intent_id=intent.id,
            stripe_error={"code": "card_declined", "decline_code": "generic_decline", "message": "Your card was declined."},
            failure_context={"source": "test"},
        )

        assert result["status"] == "failed"
        assert result["failure_reason"] == PaymentFailureReason.CARD_DECLINED.value
        await db_session.refresh(intent)
        assert intent.status == "failed"
        assert intent.failed_at is not None
        assert intent.payment_intent_metadata["failure_context"] == {"source": "test"}

    async def test_preserves_existing_metadata(self, db_session):
        user = await make_user(db_session)
        intent = await make_payment_intent(db_session, user.id, payment_intent_metadata={"original": "kept"})
        handler = PaymentFailureHandler(db_session)

        await handler.handle_failure(payment_intent_id=intent.id)

        await db_session.refresh(intent)
        assert intent.payment_intent_metadata["original"] == "kept"

    async def test_no_stripe_error_maps_to_unknown(self, db_session):
        user = await make_user(db_session)
        intent = await make_payment_intent(db_session, user.id)
        handler = PaymentFailureHandler(db_session)

        result = await handler.handle_failure(payment_intent_id=intent.id)
        assert result["failure_reason"] == PaymentFailureReason.UNKNOWN.value


class TestMapFailureReason:

    @pytest.mark.parametrize("stripe_error,expected", [
        ({"decline_code": "insufficient_funds"}, PaymentFailureReason.INSUFFICIENT_FUNDS),
        ({"message": "insufficient balance"}, PaymentFailureReason.INSUFFICIENT_FUNDS),
        ({"code": "expired_card"}, PaymentFailureReason.EXPIRED_CARD),
        ({"code": "authentication_required"}, PaymentFailureReason.AUTHENTICATION_REQUIRED),
        ({"decline_code": "fraud_suspected"}, PaymentFailureReason.FRAUD_SUSPECTED),
        ({"decline_code": "limit_exceeded"}, PaymentFailureReason.LIMIT_EXCEEDED),
        ({"message": "network timeout"}, PaymentFailureReason.NETWORK_ERROR),
        ({"message": "processing failure"}, PaymentFailureReason.PROCESSING_ERROR),
        ({"decline_code": "generic_decline", "message": "declined"}, PaymentFailureReason.CARD_DECLINED),
        ({"code": "invalid_number"}, PaymentFailureReason.INVALID_CARD),
        ({"message": "something else entirely"}, PaymentFailureReason.UNKNOWN),
        (None, PaymentFailureReason.UNKNOWN),
    ])
    def test_maps_stripe_error_to_reason(self, db_session, stripe_error, expected):
        handler = PaymentFailureHandler(db_session)
        assert handler._map_failure_reason(stripe_error) == expected


class TestUserGuidance:

    def test_every_reason_has_guidance(self, db_session):
        handler = PaymentFailureHandler(db_session)
        for reason in PaymentFailureReason:
            message, next_steps = handler._user_guidance(reason)
            assert message
            assert next_steps
