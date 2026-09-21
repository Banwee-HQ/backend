"""Tests for services/commerce/payments.py - PaymentService.

Uses Stripe's real test-mode API rather than mocking - .env.dev has a sk_test_
key, so these hit Stripe's test environment for real without touching any
actual card or charging money. See tests/api/commerce/test_payments.py for
why stripe.PaymentMethod.create() with tok_visa is used instead of the shared
named token pm_card_visa.
"""

import os
import pytest
import stripe
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timedelta

from fastapi import HTTPException
from core.utils.uuid_utils import uuid7
from services.commerce.payments import PaymentService
from models.commerce.payments import PaymentIntent, Transaction, PaymentFailureReason

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")


def fresh_stripe_payment_method_id() -> str:
    return stripe.PaymentMethod.create(type="card", card={"token": "tok_visa"}).id


@pytest.fixture
async def payment_method(db_session, test_user):
    service = PaymentService(db_session)
    return await service.create_method(
        user_id=test_user.id, stripe_payment_method_id=fresh_stripe_payment_method_id(), is_default=True
    )


@pytest.fixture
async def payment_intent(db_session, test_user):
    intent = PaymentIntent(
        id=uuid7(), stripe_payment_intent_id=f"pi_test_{uuid4().hex[:16]}", user_id=test_user.id,
        amount_breakdown={"total": 49.98, "currency": "USD"}, currency="USD", status="requires_payment_method",
    )
    db_session.add(intent)
    await db_session.commit()
    await db_session.refresh(intent)
    return intent


@pytest.fixture
async def failed_intent(db_session, test_user):
    intent = PaymentIntent(
        id=uuid7(), stripe_payment_intent_id=f"pi_test_{uuid4().hex[:16]}", user_id=test_user.id,
        amount_breakdown={"total": 49.98, "currency": "USD"}, currency="USD", status="failed",
        failed_at=datetime.utcnow(), failure_reason=PaymentFailureReason.CARD_DECLINED.value,
        failure_metadata={"retry_count": 0},
    )
    db_session.add(intent)
    await db_session.commit()
    await db_session.refresh(intent)
    return intent


@pytest.fixture
async def order(db_session, test_user):
    from models.commerce.orders import Order, OrderStatus, PaymentStatus, FulfillmentStatus
    o = Order(
        id=uuid7(), order_number=f"ORD-{uuid4().hex[:10].upper()}", user_id=test_user.id,
        order_status=OrderStatus.PENDING, payment_status=PaymentStatus.PENDING,
        fulfillment_status=FulfillmentStatus.UNFULFILLED,
        subtotal=Decimal("49.98"), shipping_cost=Decimal("0.00"), tax_amount=Decimal("0.00"),
        total_amount=Decimal("49.98"),
        billing_address={"street": "1 Test St"}, shipping_address={"street": "1 Test St"},
    )
    db_session.add(o)
    await db_session.commit()
    return o


@pytest.fixture
async def transaction(db_session, test_user):
    txn = Transaction(
        id=uuid7(), user_id=test_user.id, amount=Decimal("49.98"), currency="USD",
        status="succeeded", transaction_type="payment", description="Test payment",
    )
    db_session.add(txn)
    await db_session.commit()
    await db_session.refresh(txn)
    return txn


# ---------------------------------------------------------------------------
# Payment methods
# ---------------------------------------------------------------------------

class TestGet:

    async def test_returns_own_active_method(self, db_session, test_user, payment_method):
        service = PaymentService(db_session)
        result = await service.get(payment_method.id, test_user.id)
        assert result.id == payment_method.id

    async def test_excludes_soft_deleted(self, db_session, test_user, payment_method):
        service = PaymentService(db_session)
        await service.delete(payment_method.id, test_user.id)
        assert await service.get(payment_method.id, test_user.id) is None


class TestListMethods:

    async def test_lists_own_methods(self, db_session, test_user, payment_method):
        service = PaymentService(db_session)
        result = await service.list(test_user.id)
        assert result["pagination"]["total"] >= 1
        assert any(pm.id == payment_method.id for pm in result["data"])

    async def test_search_by_last_four(self, db_session, test_user, payment_method):
        service = PaymentService(db_session)
        result = await service.list(test_user.id, search=payment_method.last_four)
        assert any(pm.id == payment_method.id for pm in result["data"])


class TestUpdate:

    async def test_updates_expiry(self, db_session, test_user, payment_method):
        service = PaymentService(db_session)
        updated = await service.update(payment_method.id, test_user.id, {"expiry_month": 6, "expiry_year": 2099})
        assert updated.expiry_month == 6
        assert updated.expiry_year == 2099

    async def test_ignores_disallowed_fields(self, db_session, test_user, payment_method):
        service = PaymentService(db_session)
        updated = await service.update(payment_method.id, test_user.id, {"last_four": "0000"})
        assert updated.last_four != "0000"

    async def test_unknown_id_returns_none(self, db_session, test_user):
        service = PaymentService(db_session)
        assert await service.update(uuid4(), test_user.id, {"expiry_month": 1}) is None


class TestSetDefault:

    async def test_sets_new_default_and_unsets_old(self, db_session, test_user, payment_method):
        service = PaymentService(db_session)
        second = await service.create_method(
            user_id=test_user.id, stripe_payment_method_id=fresh_stripe_payment_method_id(), is_default=False
        )
        assert await service.set_default(second.id, test_user.id) is True
        await db_session.refresh(payment_method)
        await db_session.refresh(second)
        assert second.is_default is True
        assert payment_method.is_default is False

    async def test_unknown_id_returns_false(self, db_session, test_user):
        service = PaymentService(db_session)
        assert await service.set_default(uuid4(), test_user.id) is False


class TestDelete:

    async def test_soft_deletes(self, db_session, test_user, payment_method):
        service = PaymentService(db_session)
        assert await service.delete(payment_method.id, test_user.id) is True
        await db_session.refresh(payment_method)
        assert payment_method.is_active is False

    async def test_not_found_raises_404(self, db_session, test_user):
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.delete(uuid4(), test_user.id)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Payment intents
# ---------------------------------------------------------------------------

class TestCreateIntent:

    async def test_creates_a_real_stripe_intent(self, db_session, test_user):
        service = PaymentService(db_session)
        intent = await service.create_intent(user_id=test_user.id, amount=25.00, currency="USD")
        assert intent.stripe_payment_intent_id.startswith("pi_")
        assert intent.amount_breakdown["total"] == 25.00

    async def test_uncommitted_intent_is_not_persisted(self, db_session, test_user):
        service = PaymentService(db_session)
        intent = await service.create_intent(user_id=test_user.id, amount=10.00, commit=False)
        assert intent.stripe_payment_intent_id.startswith("pi_")


class TestConfirmIntent:

    async def test_confirms_successfully_with_test_card(self, db_session, test_user, payment_method):
        service = PaymentService(db_session)
        intent = await service.create_intent(user_id=test_user.id, amount=15.00)
        confirmed = await service.confirm_intent(intent.id, payment_method.stripe_payment_method_id)
        assert confirmed.status == "succeeded"
        assert confirmed.confirmed_at is not None

    async def test_not_found_raises_404(self, db_session, test_user, payment_method):
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.confirm_intent(uuid4(), payment_method.stripe_payment_method_id)
        assert exc_info.value.status_code == 404


class TestIntentCRUD:

    async def test_get_intent(self, db_session, test_user, payment_intent):
        service = PaymentService(db_session)
        result = await service.get_intent(payment_intent.id, test_user.id)
        assert result.id == payment_intent.id

    async def test_list_intents(self, db_session, test_user, payment_intent):
        service = PaymentService(db_session)
        result = await service.list_intents(test_user.id)
        assert result["total"] >= 1
        assert any(i.id == payment_intent.id for i in result["items"])

    async def test_update_intent_persists_metadata(self, db_session, test_user, payment_intent):
        """Regression test: this used to set intent.metadata/.description, neither
        of which is a real column (the real one is payment_intent_metadata) -
        every update silently discarded the change."""
        service = PaymentService(db_session)
        updated = await service.update_intent(payment_intent.id, test_user.id, {"metadata": {"note": "gift"}})
        assert updated.payment_intent_metadata == {"note": "gift"}

    async def test_update_intent_not_found_returns_none(self, db_session, test_user):
        service = PaymentService(db_session)
        assert await service.update_intent(uuid4(), test_user.id, {"metadata": {}}) is None

    async def test_delete_pending_intent(self, db_session, test_user, payment_intent):
        service = PaymentService(db_session)
        assert await service.delete_intent(payment_intent.id, test_user.id) is True

    async def test_cannot_delete_succeeded_intent(self, db_session, test_user, payment_intent):
        payment_intent.status = "succeeded"
        await db_session.commit()
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.delete_intent(payment_intent.id, test_user.id)
        assert exc_info.value.status_code == 400

    async def test_delete_intent_not_found_returns_false(self, db_session, test_user):
        service = PaymentService(db_session)
        assert await service.delete_intent(uuid4(), test_user.id) is False


# ---------------------------------------------------------------------------
# process_idempotent - the flow OrderService.create() drives checkout through
# ---------------------------------------------------------------------------

class TestProcessIdempotent:

    async def test_succeeds_with_a_real_test_card(self, db_session, test_user, payment_method, order):
        service = PaymentService(db_session)
        result = await service.process_idempotent(
            user_id=test_user.id, order_id=order.id, amount=49.98,
            payment_method_id=payment_method.id, idempotency_key=f"idem-{uuid4().hex[:12]}",
        )
        assert result["status"] == "succeeded"
        assert result["cached"] is False

    async def test_returns_cached_result_for_repeated_key(self, db_session, test_user, payment_method, order):
        service = PaymentService(db_session)
        key = f"idem-{uuid4().hex[:12]}"
        first = await service.process_idempotent(
            user_id=test_user.id, order_id=order.id, amount=49.98,
            payment_method_id=payment_method.id, idempotency_key=key,
        )
        second = await service.process_idempotent(
            user_id=test_user.id, order_id=order.id, amount=49.98,
            payment_method_id=payment_method.id, idempotency_key=key,
        )
        assert second["cached"] is True
        assert second["transaction_id"] == first["transaction_id"]

    async def test_frontend_price_mismatch_is_rejected(self, db_session, test_user, payment_method, order):
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.process_idempotent(
                user_id=test_user.id, order_id=order.id, amount=49.98,
                payment_method_id=payment_method.id, idempotency_key=f"idem-{uuid4().hex[:12]}",
                frontend_calculated_amount=1.00,
            )
        assert exc_info.value.status_code == 400

    async def test_unknown_payment_method_raises_404(self, db_session, test_user, order):
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.process_idempotent(
                user_id=test_user.id, order_id=order.id, amount=49.98,
                payment_method_id=uuid4(), idempotency_key=f"idem-{uuid4().hex[:12]}",
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

class TestTransactions:

    async def test_lists_own_transactions(self, db_session, test_user, transaction):
        service = PaymentService(db_session)
        result = await service.transactions(test_user.id)
        assert result["pagination"]["total"] >= 1
        assert any(t["id"] == str(transaction.id) for t in result["transactions"])

    async def test_all_transactions_admin_view(self, db_session, transaction):
        service = PaymentService(db_session)
        result = await service.all_transactions()
        assert result["pagination"]["total"] >= 1

    async def test_all_transactions_filters_by_status(self, db_session, transaction):
        service = PaymentService(db_session)
        result = await service.all_transactions(status="succeeded")
        assert all(t["status"] == "succeeded" for t in result["transactions"])

    async def test_get_transaction(self, db_session, test_user, transaction):
        service = PaymentService(db_session)
        result = await service.get_transaction(transaction.id, test_user.id)
        assert result.id == transaction.id

    async def test_create_transaction(self, db_session, test_user):
        service = PaymentService(db_session)
        txn = await service.create_transaction(test_user.id, {"amount": 10.0, "status": "succeeded"})
        assert txn.amount == 10.0

    async def test_update_transaction(self, db_session, test_user, transaction):
        service = PaymentService(db_session)
        updated = await service.update_transaction(transaction.id, test_user.id, {"description": "Updated"})
        assert updated.description == "Updated"

    async def test_update_transaction_not_found_returns_none(self, db_session, test_user):
        service = PaymentService(db_session)
        assert await service.update_transaction(uuid4(), test_user.id, {"description": "x"}) is None

    async def test_delete_transaction(self, db_session, test_user, transaction):
        service = PaymentService(db_session)
        assert await service.delete_transaction(transaction.id, test_user.id) is True

    async def test_delete_transaction_not_found_returns_false(self, db_session, test_user):
        service = PaymentService(db_session)
        assert await service.delete_transaction(uuid4(), test_user.id) is False


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------

class TestRefund:

    async def test_refunds_a_succeeded_payment(self, db_session, test_user, payment_method):
        service = PaymentService(db_session)
        intent = await service.create_intent(user_id=test_user.id, amount=20.00)
        confirmed = await service.confirm_intent(intent.id, payment_method.stripe_payment_method_id)
        assert confirmed.status == "succeeded"

        refund = await service.refund(confirmed.id, amount=20.00, reason="requested_by_customer")
        assert refund.transaction_type == "refund"
        assert refund.amount == -20.00

    async def test_not_found_raises_404(self, db_session):
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.refund(uuid4())
        assert exc_info.value.status_code == 404

    async def test_cannot_refund_unsuccessful_payment(self, db_session, test_user, payment_intent):
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.refund(payment_intent.id)
        assert exc_info.value.status_code == 400


class TestRefundCRUD:

    @pytest.fixture
    async def refund_transaction(self, db_session, test_user):
        txn = Transaction(
            id=uuid7(), user_id=test_user.id, amount=Decimal("-10.00"), currency="USD",
            status="succeeded", transaction_type="refund", description="Refund",
        )
        db_session.add(txn)
        await db_session.commit()
        await db_session.refresh(txn)
        return txn

    async def test_get_refund(self, db_session, test_user, refund_transaction):
        service = PaymentService(db_session)
        result = await service.get_refund(refund_transaction.id, test_user.id)
        assert result.id == refund_transaction.id

    async def test_list_refunds(self, db_session, test_user, refund_transaction):
        service = PaymentService(db_session)
        result = await service.list_refunds(test_user.id)
        assert result["total"] >= 1

    async def test_update_refund(self, db_session, test_user, refund_transaction):
        service = PaymentService(db_session)
        updated = await service.update_refund(refund_transaction.id, test_user.id, {"description": "Corrected"})
        assert updated.description == "Corrected"

    async def test_delete_refund(self, db_session, test_user, refund_transaction):
        service = PaymentService(db_session)
        assert await service.delete_refund(refund_transaction.id, test_user.id) is True


# ---------------------------------------------------------------------------
# Failure handling - retry / failure_status / failed_payments
# ---------------------------------------------------------------------------

class TestRetry:

    async def test_resets_a_failed_intent_for_retry(self, db_session, test_user, failed_intent):
        """Regression test: retry()/failure_status()/failed_payments() all read
        payment_intent.failure_metadata, a column that never existed on the
        table - every call to any of these three live endpoints crashed."""
        service = PaymentService(db_session)
        result = await service.retry(failed_intent.id)
        assert result["status"] == "ready_for_retry"
        assert result["retry_count"] == 1

    async def test_can_swap_payment_method(self, db_session, test_user, failed_intent, payment_method):
        service = PaymentService(db_session)
        await service.retry(failed_intent.id, new_payment_method_id=payment_method.id)
        await db_session.refresh(failed_intent)
        assert failed_intent.payment_method_id == payment_method.stripe_payment_method_id

    async def test_not_found_raises_404(self, db_session):
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.retry(uuid4())
        assert exc_info.value.status_code == 404

    async def test_cannot_retry_a_non_failed_intent(self, db_session, test_user, payment_intent):
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.retry(payment_intent.id)
        assert exc_info.value.status_code == 400

    async def test_non_retryable_reason_is_rejected(self, db_session, test_user, failed_intent):
        failed_intent.failure_reason = PaymentFailureReason.FRAUD_SUSPECTED.value
        await db_session.commit()
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.retry(failed_intent.id)
        assert exc_info.value.status_code == 400


class TestFailureStatus:

    async def test_reports_failure_details(self, db_session, test_user, failed_intent):
        service = PaymentService(db_session)
        result = await service.failure_status(failed_intent.id, test_user.id)
        assert result["is_failed"] is True
        assert result["failure_reason"] == PaymentFailureReason.CARD_DECLINED.value
        assert "user_message" in result

    async def test_non_failed_intent_reports_not_failed(self, db_session, test_user, payment_intent):
        service = PaymentService(db_session)
        result = await service.failure_status(payment_intent.id, test_user.id)
        assert result["is_failed"] is False

    async def test_not_found_raises_404(self, db_session, test_user):
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.failure_status(uuid4(), test_user.id)
        assert exc_info.value.status_code == 404


class TestFailedPayments:

    async def test_lists_failed_payments_with_retry_info(self, db_session, test_user, failed_intent):
        service = PaymentService(db_session)
        result = await service.failed_payments(test_user.id)
        assert result["pagination"]["total"] >= 1
        entry = next(p for p in result["failed_payments"] if p["payment_intent_id"] == str(failed_intent.id))
        assert entry["can_retry"] is True


# ---------------------------------------------------------------------------
# Pure-logic helpers
# ---------------------------------------------------------------------------

class TestCategorizeStripeError:

    def test_maps_known_error_code(self, db_session):
        service = PaymentService(db_session)

        class FakeError:
            code = "insufficient_funds"
        assert service._categorize_stripe_error(FakeError()) == PaymentFailureReason.INSUFFICIENT_FUNDS

    def test_falls_back_to_message_sniffing(self, db_session):
        service = PaymentService(db_session)

        class FakeError:
            def __str__(self):
                return "suspicious fraud activity detected"
        assert service._categorize_stripe_error(FakeError()) == PaymentFailureReason.FRAUD_SUSPECTED

    def test_unknown_error_returns_unknown(self, db_session):
        service = PaymentService(db_session)

        class FakeError:
            def __str__(self):
                return "something odd happened"
        assert service._categorize_stripe_error(FakeError()) == PaymentFailureReason.UNKNOWN


class TestDetermineRetryStrategy:

    def test_fraud_is_never_retryable(self, db_session, payment_intent):
        service = PaymentService(db_session)
        result = service._determine_retry_strategy(PaymentFailureReason.FRAUD_SUSPECTED, payment_intent)
        assert result["should_retry"] is False

    def test_max_retries_reached_blocks_retry(self, db_session, payment_intent):
        payment_intent.failure_metadata = {"retry_count": 3}
        service = PaymentService(db_session)
        result = service._determine_retry_strategy(PaymentFailureReason.CARD_DECLINED, payment_intent)
        assert result["should_retry"] is False
        assert result["max_retries_reached"] is True

    def test_retryable_reason_returns_delay(self, db_session, payment_intent):
        payment_intent.failure_metadata = None
        service = PaymentService(db_session)
        result = service._determine_retry_strategy(PaymentFailureReason.CARD_DECLINED, payment_intent)
        assert result["should_retry"] is True
        assert result["next_retry_in_hours"] == 1


class TestGetUserFriendlyMessage:

    def test_returns_a_string_for_every_reason(self, db_session):
        service = PaymentService(db_session)
        for reason in PaymentFailureReason:
            assert isinstance(service._get_user_friendly_message(reason), str)


class TestGetNextSteps:

    def test_returns_a_list_for_every_reason(self, db_session):
        service = PaymentService(db_session)
        for reason in PaymentFailureReason:
            assert isinstance(service._get_next_steps(reason), list)
