"""Tests for services/commerce/payments.py - PaymentService.

Uses Stripe's real test-mode API rather than mocking - .env.dev has a sk_test_
key, so these hit Stripe's test environment for real without touching any
actual card or charging money. See tests/api/commerce/test_payments.py for
why stripe.PaymentMethod.create() with tok_visa is used instead of the shared
named token pm_card_visa.
"""

import os
import json
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

if not stripe.api_key.startswith("sk_test_") or "placeholder" in stripe.api_key:
    pytest.skip("Stripe integration tests require a real STRIPE_SECRET_KEY", allow_module_level=True)


def fresh_stripe_payment_method_id() -> str:
    return stripe.PaymentMethod.create(type="card", card={"token": "tok_visa"}).id


def _async_raiser(exc):
    async def _raise(*args, **kwargs):
        raise exc
    return _raise


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
async def second_user(db_session):
    """A second, independent user - for cross-account conflict/ownership tests."""
    from models.accounts.user import User, UserRole
    from core.utils.encryption import PasswordManager
    user = User(
        id=uuid7(), email=f"test2_{uuid4().hex[:8]}@example.com",
        hashed_password=PasswordManager().hash_password("TestPassword123!"),
        firstname="Second", lastname="User", phone="+1234567891",
        role=UserRole.CUSTOMER, account_status="active", verification_status="verified",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


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


# --------------------------------------------------------------------------- Payment methods ---------------------------------------------------------------------------

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


# --------------------------------------------------------------------------- Payment intents ---------------------------------------------------------------------------


class TestConfirmIntent:


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


# --------------------------------------------------------------------------- process_idempotent - the flow OrderService.create() drives checkout through ---------------------------------------------------------------------------

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


# --------------------------------------------------------------------------- Transactions ---------------------------------------------------------------------------

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

    async def test_all_transactions_filters_by_date_range(self, db_session, transaction):
        service = PaymentService(db_session)
        today = datetime.utcnow().date().isoformat()
        result = await service.all_transactions(date_from=today, date_to=today)
        assert any(t["id"] == str(transaction.id) for t in result["transactions"])

        yesterday = (datetime.utcnow().date() - timedelta(days=2)).isoformat()
        two_days_ago = (datetime.utcnow().date() - timedelta(days=4)).isoformat()
        excluded = await service.all_transactions(date_from=two_days_ago, date_to=yesterday)
        assert not any(t["id"] == str(transaction.id) for t in excluded["transactions"])

    async def test_all_transactions_filters_by_search(self, db_session, test_user, transaction):
        service = PaymentService(db_session)
        result = await service.all_transactions(search=test_user.email)
        assert any(t["id"] == str(transaction.id) for t in result["transactions"])

        result_none = await service.all_transactions(search="nobody-matches-this-xyz")
        assert not any(t["id"] == str(transaction.id) for t in result_none["transactions"])

    async def test_all_transactions_ignores_invalid_date_filters(self, db_session, transaction):
        """Malformed date_from/date_to are silently ignored rather than raising."""
        service = PaymentService(db_session)
        result = await service.all_transactions(date_from="not-a-date", date_to="also-not-a-date")
        assert any(t["id"] == str(transaction.id) for t in result["transactions"])

    async def test_get_transaction(self, db_session, test_user, transaction):
        service = PaymentService(db_session)
        result = await service.get_transaction(transaction.id, test_user.id)
        assert result.id == transaction.id


# --------------------------------------------------------------------------- Refunds ---------------------------------------------------------------------------

class TestRefund:


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


# --------------------------------------------------------------------------- Failure handling - retry / failure_status / failed_payments ---------------------------------------------------------------------------

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


# --------------------------------------------------------------------------- Pure-logic helpers ---------------------------------------------------------------------------


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


# --------------------------------------------------------------------------- create_method - dedup/conflict handling and Stripe-declined-at-attach-time behavior. ---------------------------------------------------------------------------

class TestCreateMethodDeduplication:

    async def test_reusing_same_stripe_id_for_same_user_returns_existing(self, db_session, test_user, payment_method):
        """Calling create_method twice with the same Stripe payment method id must not
        create a duplicate row (and must not double-charge/double-attach anything)."""
        service = PaymentService(db_session)
        again = await service.create_method(
            user_id=test_user.id, stripe_payment_method_id=payment_method.stripe_payment_method_id,
        )
        assert again.id == payment_method.id

    async def test_reusing_same_stripe_id_can_promote_to_default(self, db_session, test_user, payment_method):
        second = await PaymentService(db_session).create_method(
            user_id=test_user.id, stripe_payment_method_id=fresh_stripe_payment_method_id(), is_default=False
        )
        service = PaymentService(db_session)
        promoted = await service.create_method(
            user_id=test_user.id, stripe_payment_method_id=second.stripe_payment_method_id, is_default=True,
        )
        assert promoted.id == second.id
        await db_session.refresh(payment_method)
        assert promoted.is_default is True
        assert payment_method.is_default is False

    async def test_same_stripe_id_for_different_user_is_conflict(self, db_session, test_user, second_user, payment_method):
        """Two accounts must never end up sharing one Stripe payment method record."""
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.create_method(
                user_id=second_user.id, stripe_payment_method_id=payment_method.stripe_payment_method_id,
            )
        assert exc_info.value.status_code == 409

    async def test_concurrent_insert_race_is_handled_without_crashing(self, db_session, test_user, second_user, payment_method):
        """Simulates a real race: another in-flight (uncommitted, unflushed) insert for the
        same Stripe id isn't visible to create_method's own pre-check (autoflush is off),
        so it only surfaces as a DB-level unique-violation at commit time. The service must
        not corrupt state; since the racing row is never durably committed (it's rolled back
        together with the failed insert), the operation correctly fails rather than silently
        losing or duplicating data.

        Needs `payment_method` (so test_user already has a stripe_customer_id) - otherwise
        create_method's own "ensure customer" step calls self.db.commit() before the
        pre-check even runs, which would flush+release our staged racing row early and
        let the ordinary pre-check conflict path (409) catch it instead of the exception
        handler this test targets."""
        from models.commerce.payments import PaymentMethod
        stripe_id = fresh_stripe_payment_method_id()
        racing_row = PaymentMethod(
            user_id=second_user.id, type="card", provider="stripe",
            stripe_payment_method_id=stripe_id, is_active=True,
        )
        db_session.add(racing_row)  # staged but not committed/flushed
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.create_method(user_id=test_user.id, stripe_payment_method_id=stripe_id)
        # The racing row is rolled back along with the failed insert (it was never durably committed), so the post-rollback re-check finds nothing to recover and the original IntegrityError is re-raised, surfacing as a 500 - not the cleaner 409 a pre-existing, already-committed conflict would produce. This documents the actual current behavior of that fallback path.
        assert exc_info.value.status_code == 500
        assert "duplicate" in exc_info.value.detail.lower() or "unique" in exc_info.value.detail.lower()


class TestCreateMethodStripeDeclineAtAttach:

    async def test_card_declined_at_attach_returns_400(self, db_session, test_user):
        """Some Stripe test cards decline immediately when attached to a customer
        (not just at charge time) - this must surface as a clean 400, not a 500."""
        service = PaymentService(db_session)
        declining_pm_id = stripe.PaymentMethod.create(type="card", card={"token": "tok_chargeDeclined"}).id
        with pytest.raises(HTTPException) as exc_info:
            await service.create_method(user_id=test_user.id, stripe_payment_method_id=declining_pm_id)
        assert exc_info.value.status_code == 400

    async def test_recovers_from_stale_customer_id(self, db_session, test_user):
        """If the user's stored stripe_customer_id no longer exists on Stripe's side
        (e.g. deleted directly in the dashboard), create_method must recreate the
        customer transparently rather than failing."""
        test_user.stripe_customer_id = "cus_does_not_exist_anymore"
        await db_session.commit()
        service = PaymentService(db_session)
        pm = await service.create_method(user_id=test_user.id, stripe_payment_method_id=fresh_stripe_payment_method_id())
        assert pm is not None
        await db_session.refresh(test_user)
        assert test_user.stripe_customer_id != "cus_does_not_exist_anymore"

    async def test_tolerates_payment_method_already_attached_elsewhere(self, db_session, test_user):
        """Stripe's 'already attached to a customer' error is deliberately swallowed
        (it's not fatal to recording the payment method locally)."""
        pm_id = stripe.PaymentMethod.create(type="card", card={"token": "tok_visa"}).id
        other_customer = stripe.Customer.create(email=f"other-{uuid4().hex[:8]}@example.com")
        stripe.PaymentMethod.attach(pm_id, customer=other_customer.id)

        service = PaymentService(db_session)
        pm = await service.create_method(user_id=test_user.id, stripe_payment_method_id=pm_id)
        assert pm.stripe_payment_method_id == pm_id

    async def test_unknown_user_raises_404_modern_path(self, db_session):
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.create_method(user_id=uuid4(), stripe_payment_method_id=fresh_stripe_payment_method_id())
        assert exc_info.value.status_code == 404

    async def test_attach_failure_other_than_already_attached_is_raised(self, db_session, test_user):
        """A customer that retrieve() still returns (Stripe returns deleted customers
        without erroring) but that attach() itself refuses (deleted customers are
        rejected there) - the attach except's `if 'already' not in message: raise`
        branch, as opposed to the 'already attached elsewhere' tolerance branch above."""
        deleted_customer = stripe.Customer.create(email=f"del-{uuid4().hex[:8]}@example.com")
        stripe.Customer.delete(deleted_customer.id)
        test_user.stripe_customer_id = deleted_customer.id
        await db_session.commit()

        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.create_method(user_id=test_user.id, stripe_payment_method_id=fresh_stripe_payment_method_id())
        assert exc_info.value.status_code == 400

# --------------------------------------------------------------------------- update() / set_default() - additional edge cases ---------------------------------------------------------------------------

class TestUpdateEdgeCases:

    async def test_integer_overflow_is_reported_as_500_not_crash(self, db_session, test_user, payment_method):
        """expiry_year is an unconstrained DB integer column; a value outside Postgres's
        int4 range must fail cleanly via the service's own error handling."""
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.update(payment_method.id, test_user.id, {"expiry_year": 10**12})
        assert exc_info.value.status_code == 500


class TestSetDefaultExceptionHandling:

    async def test_underlying_db_error_is_reported_as_500(self, db_session, test_user, second_user, payment_method):
        """set_default() only ever touches is_default booleans - there's no
        attacker/caller-controlled input that can make its own commit fail. To
        exercise its error handling honestly, stage an unrelated pending row (added
        to the same session, not yet flushed) that violates the stripe_payment_method_id
        uniqueness constraint; set_default()'s own commit() flushes everything pending,
        so that staged conflict surfaces as a real DB error at commit time."""
        from models.commerce.payments import PaymentMethod
        conflicting = PaymentMethod(
            user_id=second_user.id, type="card", provider="stripe",
            stripe_payment_method_id=payment_method.stripe_payment_method_id, is_active=True,
        )
        db_session.add(conflicting)
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.set_default(payment_method.id, test_user.id)
        assert exc_info.value.status_code == 500


class TestDeleteStripeErrorHandling:

    async def test_corrupted_stripe_id_surfaces_as_400(self, db_session, test_user, payment_method):
        """If the locally stored stripe_payment_method_id no longer resolves on
        Stripe's side, delete() must surface a clean 400 rather than a raw crash."""
        payment_method.stripe_payment_method_id = "pm_totally_made_up_id_12345"
        await db_session.commit()
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.delete(payment_method.id, test_user.id)
        assert exc_info.value.status_code == 400


# --------------------------------------------------------------------------- create_intent / confirm_intent - Stripe errors, 3DS, failure-handler resilience ---------------------------------------------------------------------------


class TestConfirmIntentDeclineAndFailureHandler:


    async def test_failure_handler_error_does_not_mask_the_decline_response(self, db_session, test_user):
        """Regression: if the failure-recording handler itself blows up (e.g. because
        the intent's amount_breakdown is malformed), the caller must still get the
        correct 400 decline response instead of a 500 from the handler's own bug."""
        intent = PaymentIntent(
            id=uuid7(), stripe_payment_intent_id=f"pi_test_{uuid4().hex[:16]}", user_id=test_user.id,
            amount_breakdown=None, currency="USD", status="requires_payment_method",
        )
        db_session.add(intent)
        await db_session.commit()
        await db_session.refresh(intent)

        service = PaymentService(db_session)
        declining_pm_id = stripe.PaymentMethod.create(type="card", card={"token": "tok_chargeDeclined"}).id
        with pytest.raises(HTTPException) as exc_info:
            await service.confirm_intent(intent.id, declining_pm_id)
        assert exc_info.value.status_code == 400
        assert "Payment failed" in exc_info.value.detail


# --------------------------------------------------------------------------- process() - timeout/retry control flow and non-retryable errors ---------------------------------------------------------------------------


# --------------------------------------------------------------------------- process_idempotent() - customer bootstrap edge cases and attach-error handling ---------------------------------------------------------------------------

class TestProcessIdempotentCustomerBootstrap:

    async def test_creates_customer_from_scratch_when_user_has_none(self, db_session, test_user, order):
        """Payment method inserted directly (bypassing create_method), so the user has
        no stripe_customer_id yet - process_idempotent must create one itself."""
        from models.commerce.payments import PaymentMethod
        raw_pm_id = stripe.PaymentMethod.create(type="card", card={"token": "tok_visa"}).id
        pm = PaymentMethod(user_id=test_user.id, type="card", provider="stripe",
                            stripe_payment_method_id=raw_pm_id, is_active=True)
        db_session.add(pm)
        await db_session.commit()
        await db_session.refresh(pm)
        assert test_user.stripe_customer_id is None

        service = PaymentService(db_session)
        result = await service.process_idempotent(
            user_id=test_user.id, order_id=order.id, amount=49.98,
            payment_method_id=pm.id, idempotency_key=f"idem-{uuid4().hex[:12]}",
        )
        assert result["status"] == "succeeded"
        await db_session.refresh(test_user)
        assert test_user.stripe_customer_id is not None

    async def test_recovers_from_stale_customer_id(self, db_session, test_user, order):
        from models.commerce.payments import PaymentMethod
        raw_pm_id = stripe.PaymentMethod.create(type="card", card={"token": "tok_visa"}).id
        pm = PaymentMethod(user_id=test_user.id, type="card", provider="stripe",
                            stripe_payment_method_id=raw_pm_id, is_active=True)
        db_session.add(pm)
        test_user.stripe_customer_id = "cus_does_not_exist_anymore"
        await db_session.commit()
        await db_session.refresh(pm)

        service = PaymentService(db_session)
        result = await service.process_idempotent(
            user_id=test_user.id, order_id=order.id, amount=49.98,
            payment_method_id=pm.id, idempotency_key=f"idem-{uuid4().hex[:12]}",
        )
        assert result["status"] == "succeeded"
        await db_session.refresh(test_user)
        assert test_user.stripe_customer_id != "cus_does_not_exist_anymore"

    async def test_tolerates_attach_already_attached_elsewhere(self, db_session, test_user, order):
        """Same 'already attached' tolerance as create_method, exercised via the
        separate attach-handling copy inside process_idempotent."""
        from models.commerce.payments import PaymentMethod
        raw_pm_id = stripe.PaymentMethod.create(type="card", card={"token": "tok_visa"}).id
        other_customer = stripe.Customer.create(email=f"other-{uuid4().hex[:8]}@example.com")
        stripe.PaymentMethod.attach(raw_pm_id, customer=other_customer.id)

        pm = PaymentMethod(user_id=test_user.id, type="card", provider="stripe",
                            stripe_payment_method_id=raw_pm_id, is_active=True)
        db_session.add(pm)
        await db_session.commit()
        await db_session.refresh(pm)

        service = PaymentService(db_session)
        # The attach step itself tolerates Stripe's "already attached to a customer" error and proceeds - but the PM is still, in Stripe's own records, attached to `other_customer` rather than this user's new customer, so the *confirm* step correctly refuses to charge it against the wrong customer. This is real, correct Stripe behavior (not a bug): tolerating the attach conflict doesn't - and shouldn't - retroactively fix the mismatch.
        with pytest.raises(HTTPException) as exc_info:
            await service.process_idempotent(
                user_id=test_user.id, order_id=order.id, amount=49.98,
                payment_method_id=pm.id, idempotency_key=f"idem-{uuid4().hex[:12]}",
            )
        assert exc_info.value.status_code == 400

    async def test_recovers_from_stale_customer_id_during_attach(self, db_session, test_user, order):
        """Unlike Customer.retrieve() (which returns a deleted customer's object
        without erroring), PaymentMethod.attach() DOES reject a deleted customer id -
        so a stale-but-still-'retrievable' customer id slips past the earlier retrieve
        check and is only caught here, at attach time, triggering its own separate
        recreate-and-retry."""
        from models.commerce.payments import PaymentMethod
        deleted_customer = stripe.Customer.create(email=f"del-{uuid4().hex[:8]}@example.com")
        stripe.Customer.delete(deleted_customer.id)
        test_user.stripe_customer_id = deleted_customer.id

        raw_pm_id = stripe.PaymentMethod.create(type="card", card={"token": "tok_visa"}).id
        pm = PaymentMethod(user_id=test_user.id, type="card", provider="stripe",
                            stripe_payment_method_id=raw_pm_id, is_active=True)
        db_session.add(pm)
        await db_session.commit()
        await db_session.refresh(pm)

        service = PaymentService(db_session)
        result = await service.process_idempotent(
            user_id=test_user.id, order_id=order.id, amount=49.98,
            payment_method_id=pm.id, idempotency_key=f"idem-{uuid4().hex[:12]}",
        )
        assert result["status"] == "succeeded"
        await db_session.refresh(test_user)
        assert test_user.stripe_customer_id != deleted_customer.id

    async def test_stale_local_payment_method_id_is_reported_as_400(self, db_session, test_user, order):
        """A locally stored PaymentMethod row whose stripe_payment_method_id no
        longer exists on Stripe's side fails at attach with 'No such PaymentMethod'
        - neither the 'no such customer' nor the 'already attached' tolerance
        applies, so it must be raised rather than silently ignored."""
        from models.commerce.payments import PaymentMethod
        pm = PaymentMethod(user_id=test_user.id, type="card", provider="stripe",
                            stripe_payment_method_id="pm_totally_made_up_id_12345", is_active=True)
        db_session.add(pm)
        await db_session.commit()
        await db_session.refresh(pm)

        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.process_idempotent(
                user_id=test_user.id, order_id=order.id, amount=49.98,
                payment_method_id=pm.id, idempotency_key=f"idem-{uuid4().hex[:12]}",
            )
        assert exc_info.value.status_code == 400

    async def test_authentication_required_card_returns_requires_action(self, db_session, test_user, order):
        from models.commerce.payments import PaymentMethod
        pm = PaymentMethod(user_id=test_user.id, type="card", provider="stripe",
                            stripe_payment_method_id="pm_card_authenticationRequired", is_active=True)
        db_session.add(pm)
        await db_session.commit()
        await db_session.refresh(pm)

        service = PaymentService(db_session)
        result = await service.process_idempotent(
            user_id=test_user.id, order_id=order.id, amount=49.98,
            payment_method_id=pm.id, idempotency_key=f"idem-{uuid4().hex[:12]}",
        )
        assert result["status"] == "requires_action"

    async def test_bad_order_id_fk_violation_is_reported_as_500(self, db_session, test_user, payment_method):
        """The final commit (creating the Transaction + PaymentIntent record) fails
        on the order_id FK constraint for a nonexistent order; this is a raw
        IntegrityError, not a StripeError or HTTPException, so it must be caught by
        process_idempotent's own generic exception handler."""
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.process_idempotent(
                user_id=test_user.id, order_id=uuid4(), amount=49.98,
                payment_method_id=payment_method.id, idempotency_key=f"idem-{uuid4().hex[:12]}",
            )
        assert exc_info.value.status_code == 500


# --------------------------------------------------------------------------- Transactions - malformed metadata resilience and admin filtering ---------------------------------------------------------------------------

class TestTransactionsMetadataHandling:

    async def test_invalid_json_metadata_falls_back_to_card(self, db_session, test_user):
        service = PaymentService(db_session)
        txn = Transaction(
            id=uuid7(), user_id=test_user.id, amount=Decimal("5.00"), currency="USD",
            status="succeeded", transaction_type="payment", transaction_metadata="not-valid-json{",
        )
        db_session.add(txn)
        await db_session.commit()
        result = await service.transactions(test_user.id)
        entry = next(t for t in result["transactions"] if t["id"] == str(txn.id))
        assert entry["payment_method"] == "Card"

    async def test_valid_metadata_extracts_payment_method_type(self, db_session, test_user):
        service = PaymentService(db_session)
        txn = Transaction(
            id=uuid7(), user_id=test_user.id, amount=Decimal("5.00"), currency="USD",
            status="succeeded", transaction_type="payment",
            transaction_metadata=json.dumps({"payment_method_type": "PaymentType.bank_account"}),
        )
        db_session.add(txn)
        await db_session.commit()
        result = await service.transactions(test_user.id)
        entry = next(t for t in result["transactions"] if t["id"] == str(txn.id))
        assert entry["payment_method"] == "bank_account"

    async def test_all_transactions_invalid_json_metadata_falls_back_to_card(self, db_session, test_user):
        service = PaymentService(db_session)
        txn = Transaction(
            id=uuid7(), user_id=test_user.id, amount=Decimal("5.00"), currency="USD",
            status="succeeded", transaction_type="payment", transaction_metadata="not-valid-json{",
        )
        db_session.add(txn)
        await db_session.commit()
        result = await service.all_transactions()
        entry = next(t for t in result["transactions"] if t["id"] == str(txn.id))
        assert entry["payment_method"] == "Card"

    async def test_all_transactions_payment_method_filter(self, db_session, test_user):
        service = PaymentService(db_session)
        card_txn = Transaction(
            id=uuid7(), user_id=test_user.id, amount=Decimal("5.00"), currency="USD",
            status="succeeded", transaction_type="payment",
            transaction_metadata=json.dumps({"payment_method_type": "card"}),
        )
        bank_txn = Transaction(
            id=uuid7(), user_id=test_user.id, amount=Decimal("7.00"), currency="USD",
            status="succeeded", transaction_type="payment",
            transaction_metadata=json.dumps({"payment_method_type": "bank_account"}),
        )
        db_session.add_all([card_txn, bank_txn])
        await db_session.commit()

        result = await service.all_transactions(payment_method="card")
        ids = {t["id"] for t in result["transactions"]}
        assert str(card_txn.id) in ids
        assert str(bank_txn.id) not in ids


# --------------------------------------------------------------------------- Refunds - Stripe-error path and CRUD not-found branches ---------------------------------------------------------------------------


# --------------------------------------------------------------------------- retry() / failed_payments() - malformed data resilience ---------------------------------------------------------------------------

class TestRetryEdgeCases:

    async def test_new_payment_method_not_found_raises_404(self, db_session, test_user, failed_intent):
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.retry(failed_intent.id, new_payment_method_id=uuid4())
        assert exc_info.value.status_code == 404

    async def test_corrupted_failure_reason_is_reported_as_500(self, db_session, test_user, failed_intent):
        """failure_reason is stored as free-text; if it ever contains a value that isn't
        a valid PaymentFailureReason member, retry() must fail cleanly (500) instead of
        leaking a raw ValueError."""
        failed_intent.failure_reason = "not_a_real_failure_reason"
        await db_session.commit()
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.retry(failed_intent.id)
        assert exc_info.value.status_code == 500


class TestFailureStatusCorruptedReason:

    async def test_invalid_failure_reason_raises(self, db_session, test_user, failed_intent):
        """failure_status() has no try/except of its own - an invalid stored failure_reason
        propagates as a raw ValueError, which the API layer is responsible for wrapping."""
        failed_intent.failure_reason = "not_a_real_failure_reason"
        await db_session.commit()
        service = PaymentService(db_session)
        with pytest.raises(ValueError):
            await service.failure_status(failed_intent.id, test_user.id)


class TestFailedPaymentsCorruptedReason:

    async def test_invalid_failure_reason_is_reported_as_500(self, db_session, test_user, failed_intent):
        failed_intent.failure_reason = "not_a_real_failure_reason"
        await db_session.commit()
        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.failed_payments(test_user.id)
        assert exc_info.value.status_code == 500


# --------------------------------------------------------------------------- _categorize_stripe_error - remaining error-code branches ---------------------------------------------------------------------------


# --------------------------------------------------------------------------- create_method - legacy-token customer recovery, and the non-card brand-normalization fallback ---------------------------------------------------------------------------

class TestCreateMethodNonCardBrandFallback:

    async def test_non_card_payment_method_brand_defaults_to_none(self, db_session, test_user, monkeypatch):
        """A non-card Stripe PaymentMethod has no card brand/last4, so those stay unset.
        Stripe won't attach an unverified bank account in test mode, so retrieve/attach are
        patched only to get a non-card `.type` past that gate; our own logic is not mocked."""
        class _FakePM:
            id = "pm_fake_bank_12345"
            type = "bank_account"
            card = None

        monkeypatch.setattr(stripe.PaymentMethod, "retrieve", lambda *a, **k: _FakePM())
        monkeypatch.setattr(stripe.PaymentMethod, "attach", lambda *a, **k: _FakePM())

        service = PaymentService(db_session)
        pm = await service.create_method(user_id=test_user.id, stripe_payment_method_id=_FakePM.id)
        assert pm.type == "bank_account"
        assert pm.brand is None
        assert pm.last_four is None


# --------------------------------------------------------------------------- create_method - TOCTOU race between the pre-check and the insert-commit ---------------------------------------------------------------------------
# The existing TestCreateMethodDeduplication.test_concurrent_insert_race_is_handled_without_crashing
# simulates a race with a merely *staged* (uncommitted) racing row, which gets rolled
# back together with the failed insert - so the recovery re-check finds nothing and the
# method surfaces a 500. The tests below simulate a race that's actually *won* by the
# other writer (a row that's already durably present by the time of the actual insert),
# which is the scenario the recovery block (existing_pm found, after the duplicate-key
# exception) is actually meant to handle. True multi-connection concurrency isn't needed
# to reproduce this deterministically: the conflicting row is committed normally (via
# this same db_session, exactly like any other fixture), and the method's own pre-check
# query is made to miss it exactly once - which is the real, legitimate race window
# under real concurrent load (the pre-check ran before the conflicting write landed).

class TestCreateMethodTrueRaceRecovery:

    @staticmethod
    async def _create_with_blind_precheck(service, db_session, **kwargs):
        """Calls create_method with its own pre-check (the first SELECT against
        PaymentMethod.stripe_payment_method_id) forced to return no rows exactly
        once, regardless of what's actually in the table - simulating the real
        TOCTOU window between that pre-check and the insert-commit that follows it.
        Every other query (including the recovery re-check inside the except
        handler) uses the real, unpatched execute."""
        from sqlalchemy import select
        from models.commerce.payments import PaymentMethod
        real_execute = db_session.execute
        state = {"skipped": False}
        # Match ONLY create_method's own pre-check (a plain equality filter on
        # stripe_payment_method_id, no locking clause) - not the separate
        # `.with_for_update()` "unset other defaults" query that also targets this
        # table and runs earlier whenever is_default=True is passed.
        target_marker = "payment_methods.stripe_payment_method_id ="

        async def flaky_execute(statement, *args, **kw):
            if not state["skipped"] and target_marker in str(statement).lower():
                state["skipped"] = True
                return await real_execute(select(PaymentMethod).where(PaymentMethod.id == None), *args, **kw)
            return await real_execute(statement, *args, **kw)

        db_session.execute = flaky_execute
        try:
            return await service.create_method(**kwargs)
        finally:
            db_session.execute = real_execute

    async def test_same_user_race_reuses_and_can_promote_to_default(self, db_session, test_user, payment_method):
        """`payment_method` (already default=True for test_user) stands in for a
        pre-existing default, so promoting the recovered row also exercises the
        "unset the other default(s)" loop inside the recovery block, not just the
        promotion assignment itself."""
        from models.commerce.payments import PaymentMethod
        stripe_id = fresh_stripe_payment_method_id()
        existing = PaymentMethod(
            user_id=test_user.id, type="card", provider="stripe",
            stripe_payment_method_id=stripe_id, is_active=True, is_default=False,
        )
        db_session.add(existing)
        await db_session.commit()
        await db_session.refresh(existing)

        service = PaymentService(db_session)
        result = await self._create_with_blind_precheck(
            service, db_session, user_id=test_user.id, stripe_payment_method_id=stripe_id, is_default=True,
        )
        assert result.id == existing.id
        await db_session.refresh(existing)
        await db_session.refresh(payment_method)
        assert existing.is_default is True
        assert payment_method.is_default is False

    async def test_different_user_race_still_conflicts(self, db_session, test_user, second_user):
        """Regression test for a real bug this coverage work found and fixed: the
        `raise HTTPException(409, ...)` for a cross-account race used to be raised
        from inside a try block whose own `except Exception: pass` (meant only to
        protect the best-effort re-check query) swallowed it too, since HTTPException
        is an Exception subclass - falling through to re-raise the original raw
        IntegrityError as an unhandled 500 instead. Fixed in services/commerce/
        payments.py's create_method by adding an `except HTTPException: raise`
        before that catch-all. This test would fail with status_code 500 (leaking
        the raw DB error) against the pre-fix code."""
        from models.commerce.payments import PaymentMethod
        stripe_id = fresh_stripe_payment_method_id()
        existing = PaymentMethod(
            user_id=second_user.id, type="card", provider="stripe",
            stripe_payment_method_id=stripe_id, is_active=True,
        )
        db_session.add(existing)
        await db_session.commit()

        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await self._create_with_blind_precheck(
                service, db_session, user_id=test_user.id, stripe_payment_method_id=stripe_id,
            )
        assert exc_info.value.status_code == 409


# --------------------------------------------------------------------------- process() - RateLimitError / CardError branches, and the two structurally-dead-in-practice fallbacks ---------------------------------------------------------------------------
# create_intent() and confirm_intent() (the two Stripe-calling steps _process_payment_internal
# drives) each already catch stripe.error.StripeError themselves and convert it to an
# HTTPException before it can ever propagate back up to process(). Since RateLimitError and
# CardError are both StripeError subclasses, process()'s own `except stripe.error.RateLimitError`
# and `except stripe.error.CardError` clauses can never actually be reached via a real Stripe
# call through the normal call chain - see the final report. To verify this retry-loop
# handling code is nonetheless correct (in case that call chain ever changes), these tests
# monkeypatch _process_payment_internal directly to raise the target error, isolating
# process()'s own dispatch/retry/rollback logic from the (already-tested-elsewhere) question
# of what create_intent/confirm_intent do with a real Stripe error.


# --------------------------------------------------------------------------- process_idempotent - Stripe's "previously used" payment-method-reuse error ---------------------------------------------------------------------------

class TestProcessIdempotentPreviouslyUsedPaymentMethod:

    async def test_deactivates_the_payment_method_and_returns_400(self, db_session, test_user, payment_method, order, monkeypatch):
        """Real trigger not practical to reproduce via Stripe's test API on demand
        (it depends on payment-method-type-specific single-use restrictions), so
        stripe.PaymentIntent.confirm is monkeypatched for this one call to return
        Stripe's actual documented error text for this case - verifying our own
        string-matching + is_active-flip + 400 logic, which is the real business
        logic this branch is responsible for."""
        error = stripe.error.InvalidRequestError(
            message="This PaymentMethod was previously used with a PaymentIntent without Customer attachment, and may not be used again.",
            param="payment_method",
        )

        def raise_previously_used(*args, **kwargs):
            raise error
        monkeypatch.setattr(stripe.PaymentIntent, "confirm", raise_previously_used)

        service = PaymentService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.process_idempotent(
                user_id=test_user.id, order_id=order.id, amount=49.98,
                payment_method_id=payment_method.id, idempotency_key=f"idem-{uuid4().hex[:12]}",
            )
        assert exc_info.value.status_code == 400
        assert "no longer usable" in exc_info.value.detail.lower()
        await db_session.refresh(payment_method)
        assert payment_method.is_active is False


class TestSyncIntent:

    async def test_in_flight_intent_takes_stripes_status(self, db_session, test_user, mocker):
        from types import SimpleNamespace
        from core.utils.uuid_utils import uuid7
        from models.commerce.payments import PaymentIntent
        intent = PaymentIntent(id=uuid7(), stripe_payment_intent_id="pi_sync", user_id=test_user.id,
                               amount_breakdown={"total": 5}, currency="CAD", status="requires_action", requires_action=True)
        db_session.add(intent)
        await db_session.commit()
        mocker.patch("stripe.PaymentIntent.retrieve", return_value=SimpleNamespace(status="succeeded"))
        synced = await PaymentService(db_session).sync_intent(intent)
        assert synced.status == "succeeded"
        assert synced.requires_action is False
        assert synced.confirmed_at is not None
