"""Tests for services/commerce/subscriptions_scheduler.py - renewals against Stripe test mode."""

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import stripe
from dateutil.relativedelta import relativedelta
from sqlalchemy import select

from core.utils.uuid_utils import uuid7
from models.catalog.category import Category
from models.catalog.inventories import Inventory
from models.catalog.product import Product, ProductVariant
from models.commerce.orders import Order, OrderStatus, PaymentStatus
from models.commerce.payments import CardBrand, PaymentIntent, PaymentMethod, PaymentProvider, PaymentType, Transaction
from models.commerce.subscriptions import Subscription
from services.commerce.payments import PaymentService
from services.commerce.subscriptions import SubscriptionService
from services.commerce.subscriptions_scheduler import SubscriptionScheduler, _advance, renewal_lock

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

if not stripe.api_key.startswith("sk_test_") or "placeholder" in stripe.api_key:
    pytest.skip("Stripe integration tests require a real STRIPE_SECRET_KEY", allow_module_level=True)


@pytest.fixture(autouse=True)
def quiet_emails(mocker):
    """Brevo isn't reachable from tests; the calls themselves are asserted where they matter."""
    return {
        "failed": mocker.patch("services.accounts.email.EmailService.send_subscription_payment_failed", return_value=None),
        "reminder": mocker.patch("services.accounts.email.EmailService.send_subscription_reminder", return_value=None),
        "confirmation": mocker.patch("services.commerce.orders.OrderService._send_confirmation_email", return_value=None),
    }


async def make_variant(db_session, stock: int = 50, price: str = "19.99") -> ProductVariant:
    category = Category(id=uuid7(), name="Cat", slug=f"cat-{uuid4().hex[:8]}")
    product = Product(id=uuid7(), name="Widget", slug=f"widget-{uuid4().hex[:8]}", category_id=category.id)
    variant = ProductVariant(id=uuid7(), product_id=product.id, sku=f"SKU-{uuid4().hex[:8]}", name="Default", base_price=Decimal(price))
    db_session.add_all([category, product, variant])
    await db_session.flush()
    db_session.add(Inventory(id=uuid7(), variant_id=variant.id, quantity_available=stock))
    await db_session.commit()
    return variant


async def add_card(db_session, user, token: str = "tok_visa", default: bool = True) -> PaymentMethod:
    """A saved card; tok_chargeCustomerFail attaches fine but every charge is declined."""
    if default:
        for card in (await db_session.execute(select(PaymentMethod).where(PaymentMethod.user_id == user.id))).scalars():
            card.is_default = False
    card = PaymentMethod(
        id=uuid7(), user_id=user.id, type=PaymentType.CARD, provider=PaymentProvider.STRIPE,
        last_four="4242", expiry_month=12, expiry_year=2099, brand=CardBrand.VISA,
        stripe_payment_method_id=stripe.PaymentMethod.create(type="card", card={"token": token}).id,
        is_default=default, is_active=True,
    )
    db_session.add(card)
    await db_session.commit()
    return card


async def stock_of(db_session, variant) -> int:
    inventory = (await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))).scalar_one()
    await db_session.refresh(inventory)
    return inventory.quantity_available


async def orders_of(db_session, subscription) -> list:
    return (await db_session.execute(
        select(Order).where(Order.subscription_id == subscription.id).order_by(Order.created_at)
    )).scalars().all()


async def make_due_retry(db_session, subscription) -> None:
    subscription.next_retry_date = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()


@pytest.fixture
async def variant(db_session) -> ProductVariant:
    return await make_variant(db_session)


@pytest.fixture
async def subscription(db_session, test_user, variant) -> Subscription:
    sub = await SubscriptionService(db_session).create(
        user_id=test_user.id, name="Pantry", variant_ids=[str(variant.id)], variant_quantities={str(variant.id): 2},
    )
    sub.next_billing_date = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.commit()
    await db_session.refresh(sub)
    return sub


class TestSuccessfulRenewal:

    async def test_charges_the_card_and_creates_a_paid_order(self, db_session, test_user, variant, subscription):
        await add_card(db_session, test_user)
        due = subscription.next_billing_date

        assert await SubscriptionScheduler(db_session).process_subscription(subscription.id) == "paid"

        [order] = await orders_of(db_session, subscription)
        assert order.order_number.startswith("SUB-")
        assert (order.order_status, order.payment_status) == (OrderStatus.CONFIRMED, PaymentStatus.PAID)
        assert float(order.subtotal) == pytest.approx(39.98)
        assert await stock_of(db_session, variant) == 48
        intent = (await db_session.execute(select(PaymentIntent).where(PaymentIntent.order_id == order.id))).scalar_one()
        assert intent.status == "succeeded" and intent.subscription_id == subscription.id
        payment = (await db_session.execute(select(Transaction).where(Transaction.order_id == order.id))).scalar_one()
        assert payment.status == "succeeded"

        await db_session.refresh(subscription)
        assert subscription.status == "active"
        assert subscription.payment_retry_count == 0
        assert subscription.next_billing_date == due + relativedelta(months=1)
        assert subscription.subscription_metadata["orders_created_count"] == 1

    async def test_running_again_does_not_charge_twice(self, db_session, test_user, subscription):
        await add_card(db_session, test_user)
        scheduler = SubscriptionScheduler(db_session)
        assert await scheduler.process_subscription(subscription.id) == "paid"
        assert await scheduler.process_subscription(subscription.id) == "skipped"
        assert len(await orders_of(db_session, subscription)) == 1

    async def test_first_delivery_is_on_the_start_date(self, db_session, test_user, variant):
        start = datetime.now(timezone.utc) + timedelta(days=5)
        sub = await SubscriptionService(db_session).create(
            user_id=test_user.id, name="Later", variant_ids=[str(variant.id)], current_period_start=start.date().isoformat(),
        )
        assert sub.next_billing_date.date() == start.date()

    async def test_only_in_stock_items_are_delivered_and_charged(self, db_session, test_user, variant, subscription):
        sold_out = await make_variant(db_session, stock=0, price="5.00")
        subscription.variant_ids = [str(variant.id), str(sold_out.id)]
        await db_session.commit()
        await add_card(db_session, test_user)

        assert await SubscriptionScheduler(db_session).process_subscription(subscription.id) == "paid"
        [order] = await orders_of(db_session, subscription)
        assert float(order.subtotal) == pytest.approx(39.98)

    async def test_nothing_in_stock_skips_the_delivery_without_charging(self, db_session, test_user, variant, subscription):
        inventory = (await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))).scalar_one()
        inventory.quantity_available = 0
        await db_session.commit()
        await add_card(db_session, test_user)
        due = subscription.next_billing_date

        assert await SubscriptionScheduler(db_session).process_subscription(subscription.id) == "skipped"
        assert await orders_of(db_session, subscription) == []
        await db_session.refresh(subscription)
        assert subscription.next_billing_date == due + relativedelta(months=1)


class TestDeclinedRenewal:

    async def test_decline_keeps_the_order_open_and_retries_in_6_hours(self, db_session, test_user, variant, subscription, quiet_emails):
        await add_card(db_session, test_user, "tok_chargeCustomerFail")

        assert await SubscriptionScheduler(db_session).process_subscription(subscription.id) == "declined"

        [order] = await orders_of(db_session, subscription)
        assert order.payment_status == PaymentStatus.PENDING
        assert await stock_of(db_session, variant) == 48  # held for the retry
        intent = (await db_session.execute(select(PaymentIntent).where(PaymentIntent.order_id == order.id))).scalar_one()
        assert intent.status == "failed" and intent.failure_reason
        await db_session.refresh(subscription)
        assert subscription.status == "payment_failed"
        assert subscription.payment_retry_count == 1
        assert timedelta(hours=5, minutes=59) < subscription.next_retry_date - datetime.now(timezone.utc) <= timedelta(hours=6)
        assert quiet_emails["failed"].call_args.kwargs["retry_count"] == 1

    async def test_uses_the_newest_card_when_none_is_marked_default(self, db_session, test_user, subscription):
        await add_card(db_session, test_user, default=False)
        assert await SubscriptionScheduler(db_session).process_subscription(subscription.id) == "paid"

    async def test_no_saved_card_is_a_failed_attempt(self, db_session, subscription):
        assert await SubscriptionScheduler(db_session).process_subscription(subscription.id) == "declined"
        await db_session.refresh(subscription)
        assert subscription.status == "payment_failed"
        assert "no saved card" in subscription.last_payment_error

    async def test_card_needing_the_bank_check_is_declined_off_session(self, db_session, test_user, subscription):
        await add_card(db_session, test_user, "tok_threeDSecure2Required")
        assert await SubscriptionScheduler(db_session).process_subscription(subscription.id) == "declined"
        [order] = await orders_of(db_session, subscription)
        intent = (await db_session.execute(select(PaymentIntent).where(PaymentIntent.order_id == order.id))).scalar_one()
        assert intent.failure_reason == "authentication_required"

    async def test_retry_reuses_the_same_order_and_intent(self, db_session, test_user, variant, subscription):
        await add_card(db_session, test_user, "tok_chargeCustomerFail")
        scheduler = SubscriptionScheduler(db_session)
        assert await scheduler.process_subscription(subscription.id) == "declined"

        await add_card(db_session, test_user)  # the customer adds a working card
        await make_due_retry(db_session, subscription)
        assert await scheduler.process_subscription(subscription.id) == "paid"

        [order] = await orders_of(db_session, subscription)
        assert order.payment_status == PaymentStatus.PAID
        assert len((await db_session.execute(select(PaymentIntent).where(PaymentIntent.order_id == order.id))).scalars().all()) == 1
        assert await stock_of(db_session, variant) == 48
        await db_session.refresh(subscription)
        assert (subscription.status, subscription.payment_retry_count, subscription.next_retry_date) == ("active", 0, None)

    async def test_third_decline_pauses_and_gives_the_stock_back(self, db_session, test_user, variant, subscription, quiet_emails):
        await add_card(db_session, test_user, "tok_chargeCustomerFail")
        scheduler = SubscriptionScheduler(db_session)
        for attempt in range(3):
            if attempt:
                await make_due_retry(db_session, subscription)
            assert await scheduler.process_subscription(subscription.id) == "declined"

        await db_session.refresh(subscription)
        assert subscription.status == "paused"
        assert subscription.next_retry_date is None
        [order] = await orders_of(db_session, subscription)
        assert (order.order_status, order.payment_status) == (OrderStatus.CANCELLED, PaymentStatus.FAILED)
        assert await stock_of(db_session, variant) == 50
        intent = (await db_session.execute(select(PaymentIntent).where(PaymentIntent.order_id == order.id))).scalar_one()
        assert intent.status == "canceled"
        assert quiet_emails["failed"].call_args.kwargs["retry_count"] == 3
        assert await scheduler.process_subscription(subscription.id) == "skipped"

    async def test_customer_pays_again_and_the_renewal_completes(self, db_session, test_user, subscription):
        await add_card(db_session, test_user, "tok_chargeCustomerFail")
        assert await SubscriptionScheduler(db_session).process_subscription(subscription.id) == "declined"
        due = subscription.next_billing_date

        payments = PaymentService(db_session)
        [failed] = (await payments.failed_payments(test_user.id))["failed_payments"]
        assert failed["can_retry"] is True
        card = await add_card(db_session, test_user, default=False)
        await payments.retry(failed["payment_intent_id"], card.id)
        intent = await payments.confirm_intent(failed["payment_intent_id"], str(card.id))

        assert intent.status == "succeeded"
        [order] = await orders_of(db_session, subscription)
        assert order.payment_status == PaymentStatus.PAID
        await db_session.refresh(subscription)
        assert subscription.status == "active"
        assert subscription.next_billing_date == due + relativedelta(months=1)
        assert (await payments.failed_payments(test_user.id))["failed_payments"] == []


class TestLifecycle:

    async def test_cancelling_drops_an_unpaid_renewal(self, db_session, test_user, variant, subscription):
        await add_card(db_session, test_user, "tok_chargeCustomerFail")
        await SubscriptionScheduler(db_session).process_subscription(subscription.id)

        await SubscriptionService(db_session).cancel(subscription.id, test_user.id)

        [order] = await orders_of(db_session, subscription)
        assert order.order_status == OrderStatus.CANCELLED
        assert await stock_of(db_session, variant) == 50

    async def test_pausing_after_a_decline_is_allowed(self, db_session, test_user, subscription):
        await SubscriptionScheduler(db_session).process_subscription(subscription.id)
        paused = await SubscriptionService(db_session).pause(subscription.id, test_user.id)
        assert paused.status == "paused"

    async def test_resuming_keeps_a_future_date_and_resets_retries(self, db_session, test_user, subscription):
        service = SubscriptionService(db_session)
        future = datetime.now(timezone.utc) + timedelta(days=10)
        subscription.next_billing_date = future
        subscription.payment_retry_count = 2
        await db_session.commit()
        await service.pause(subscription.id, test_user.id)
        resumed = await service.resume(subscription.id, test_user.id)
        assert resumed.next_billing_date == future
        assert resumed.payment_retry_count == 0

    async def test_resuming_after_a_missed_date_delivers_on_the_next_run(self, db_session, test_user, subscription):
        service = SubscriptionService(db_session)
        await service.pause(subscription.id, test_user.id)
        resumed = await service.resume(subscription.id, test_user.id)
        assert resumed.next_billing_date <= datetime.now(timezone.utc)

    def test_advance_never_lands_in_the_past(self):
        now = datetime.now(timezone.utc)
        sub = Subscription(billing_cycle="weekly", next_billing_date=now - timedelta(days=30), subscription_metadata={"skipped_from_date": "x"})
        _advance(sub, now, delivered=True)
        assert now < sub.next_billing_date <= now + timedelta(weeks=1)
        assert "skipped_from_date" not in sub.subscription_metadata


class TestBatch:

    async def test_processes_every_due_subscription_and_survives_errors(self, db_session, test_user, variant, subscription, mocker):
        await add_card(db_session, test_user)
        other = await SubscriptionService(db_session).create(user_id=test_user.id, name="Other", variant_ids=[str(variant.id)])
        other.next_billing_date = datetime.now(timezone.utc) - timedelta(hours=1)
        await db_session.commit()

        real = SubscriptionScheduler.process_subscription
        async def flaky(self, subscription_id):
            if subscription_id == other.id:
                raise RuntimeError("boom")
            return await real(self, subscription_id)
        mocker.patch.object(SubscriptionScheduler, "process_subscription", flaky)

        result = await SubscriptionScheduler(db_session).process_due_subscriptions()
        assert result["paid"] >= 1 and result["error"] >= 1

    async def test_due_list_loads_for_the_admin_page(self, db_session, subscription):
        due = await SubscriptionService(db_session).list_due()
        assert any(s.id == subscription.id for s in due)
        assert all(s.to_dict()["id"] for s in due)

    async def test_not_yet_due_is_left_alone(self, db_session, test_user, subscription):
        subscription.next_billing_date = datetime.now(timezone.utc) + timedelta(days=1)
        await db_session.commit()
        assert await SubscriptionScheduler(db_session).process_subscription(subscription.id) == "skipped"

    async def test_only_one_process_holds_the_renewal_lock(self, db_session):
        async with renewal_lock(db_session) as first:
            async with renewal_lock(db_session) as second:
                assert (first, second) == (True, False)


class TestReminders:

    async def test_reminds_once_per_delivery(self, db_session, subscription, quiet_emails):
        subscription.next_billing_date = datetime.now(timezone.utc) + timedelta(days=2)
        await db_session.commit()
        scheduler = SubscriptionScheduler(db_session)
        assert await scheduler.send_upcoming_reminders() >= 1
        assert quiet_emails["reminder"].call_args.kwargs["subscription_name"] == "Pantry"
        calls = quiet_emails["reminder"].call_count
        await scheduler.send_upcoming_reminders()
        assert quiet_emails["reminder"].call_count == calls

    async def test_deliveries_further_out_are_not_reminded_yet(self, db_session, subscription, quiet_emails):
        subscription.next_billing_date = datetime.now(timezone.utc) + timedelta(days=10)
        await db_session.commit()
        await SubscriptionScheduler(db_session).send_upcoming_reminders()
        assert all(c.kwargs["subscription_id"] != str(subscription.id) for c in quiet_emails["reminder"].call_args_list)
