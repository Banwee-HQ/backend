"""Tests for services/commerce/subscriptions_scheduler.py - SubscriptionScheduler."""

import os
import pytest
import stripe
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from core.utils.uuid_utils import uuid7
from services.commerce.subscriptions import SubscriptionService
from services.commerce.subscriptions_scheduler import SubscriptionScheduler, process_subscription_shipments
from models.commerce.subscriptions import Subscription
from models.commerce.payments import PaymentMethod, PaymentType, PaymentProvider, CardBrand
from models.catalog.category import Category
from models.catalog.product import Product, ProductVariant
from models.catalog.inventories import Inventory
from models.accounts.user import Address

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")


def fresh_stripe_payment_method_id() -> str:
    return stripe.PaymentMethod.create(type="card", card={"token": "tok_visa"}).id


@pytest.fixture
async def variant(db_session) -> ProductVariant:
    category = Category(id=uuid7(), name="Cat", slug=f"cat-{uuid4().hex[:8]}")
    product = Product(id=uuid7(), name="Widget", slug=f"widget-{uuid4().hex[:8]}", category_id=category.id)
    v = ProductVariant(id=uuid7(), product_id=product.id, sku=f"SKU-{uuid4().hex[:8]}", name="Default", base_price=Decimal("19.99"))
    db_session.add_all([category, product, v])
    await db_session.flush()
    db_session.add(Inventory(id=uuid7(), variant_id=v.id, quantity_available=50))
    await db_session.commit()
    return v


@pytest.fixture
async def payment_method(db_session, test_user) -> PaymentMethod:
    pm = PaymentMethod(
        id=uuid7(), user_id=test_user.id, type=PaymentType.CARD, provider=PaymentProvider.STRIPE,
        last_four="4242", expiry_month=12, expiry_year=2099, brand=CardBrand.VISA,
        stripe_payment_method_id=fresh_stripe_payment_method_id(), is_default=True, is_active=True,
    )
    db_session.add(pm)
    await db_session.commit()
    return pm


@pytest.fixture
async def subscription(db_session, test_user, variant) -> Subscription:
    service = SubscriptionService(db_session)
    sub = await service.create(user_id=test_user.id, name="Due Sub", variant_ids=[str(variant.id)])
    sub.next_billing_date = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.commit()
    await db_session.refresh(sub)
    return sub


class TestProcessSubscription:

    async def test_successful_billing_creates_order(self, db_session, test_user, variant, payment_method, subscription):
        scheduler = SubscriptionScheduler(db_session)
        result = await scheduler.process_subscription(subscription.id)
        assert result["success"] is True
        assert result["order_number"].startswith("SUB-")
        await db_session.refresh(subscription)
        assert subscription.payment_retry_count == 0
        assert subscription.status == "active"

    async def test_inactive_subscription_is_skipped(self, db_session, subscription):
        subscription.status = "paused"
        await db_session.commit()
        scheduler = SubscriptionScheduler(db_session)
        result = await scheduler.process_subscription(subscription.id)
        assert result["success"] is False
        assert "not active" in result["message"]

    async def test_auto_renew_disabled_is_skipped(self, db_session, subscription):
        subscription.auto_renew = False
        await db_session.commit()
        scheduler = SubscriptionScheduler(db_session)
        result = await scheduler.process_subscription(subscription.id)
        assert result["success"] is False
        assert "Auto-renew" in result["message"]

    async def test_no_payment_method_fails_gracefully(self, db_session, test_user, variant, subscription):
        scheduler = SubscriptionScheduler(db_session)
        result = await scheduler.process_subscription(subscription.id)
        assert result["success"] is False
        assert "payment method" in result["error"].lower()

    async def test_first_payment_failure_schedules_retry_in_6_hours(self, db_session, test_user, variant, subscription, mocker):
        mocker.patch(
            "services.commerce.payments.PaymentService.process_idempotent",
            return_value={"status": "failed", "error": "Card declined"},
        )
        pm = PaymentMethod(
            id=uuid7(), user_id=test_user.id, type=PaymentType.CARD, provider=PaymentProvider.STRIPE,
            last_four="0002", expiry_month=12, expiry_year=2099, brand=CardBrand.VISA,
            stripe_payment_method_id=f"pm_test_{uuid4().hex[:16]}", is_default=True, is_active=True,
        )
        db_session.add(pm)
        await db_session.commit()

        scheduler = SubscriptionScheduler(db_session)
        result = await scheduler.process_subscription(subscription.id)
        assert result["success"] is False
        assert result["retry_count"] == 1

        await db_session.refresh(subscription)
        assert subscription.status == "payment_failed"
        assert subscription.next_retry_date is not None
        hours_until_retry = (subscription.next_retry_date - datetime.now(timezone.utc)).total_seconds() / 3600
        assert 5.9 <= hours_until_retry <= 6.1

    async def test_third_payment_failure_pauses_subscription(self, db_session, test_user, variant, subscription, mocker):
        mocker.patch(
            "services.commerce.payments.PaymentService.process_idempotent",
            return_value={"status": "failed", "error": "Card declined"},
        )
        mocker.patch("services.accounts.email.EmailService.send_subscription_payment_failed", return_value=None)
        pm = PaymentMethod(
            id=uuid7(), user_id=test_user.id, type=PaymentType.CARD, provider=PaymentProvider.STRIPE,
            last_four="0002", expiry_month=12, expiry_year=2099, brand=CardBrand.VISA,
            stripe_payment_method_id=f"pm_test_{uuid4().hex[:16]}", is_default=True, is_active=True,
        )
        db_session.add(pm)
        subscription.payment_retry_count = 2
        await db_session.commit()

        scheduler = SubscriptionScheduler(db_session)
        result = await scheduler.process_subscription(subscription.id)
        assert result["success"] is False

        await db_session.refresh(subscription)
        assert subscription.status == "paused"
        assert subscription.next_retry_date is None
        assert "3 attempts" in subscription.pause_reason

    async def test_finalization_failure_after_successful_charge_pauses_instead_of_leaving_it_rebillable(
        self, db_session, test_user, variant, payment_method, subscription, mocker
    ):
        """Regression test: Stripe is charged before the order is finalized
        (items, inventory, next_billing_date). If finalization then failed,
        the old code rolled back only the in-memory finalization work - the
        Transaction record from the already-successful charge stayed
        committed, but next_billing_date was never advanced, so the
        subscription looked "due" again on the very next scheduler run,
        which would generate a fresh idempotency key and charge the
        customer a second time. Verifies a finalization failure now pauses
        the subscription (removing it from the due query) instead."""
        mocker.patch(
            "services.catalog.inventory.InventoryService.adjust_stock",
            side_effect=Exception("Simulated inventory failure"),
        )

        scheduler = SubscriptionScheduler(db_session)
        result = await scheduler.process_subscription(subscription.id)

        assert result["success"] is False
        assert result.get("needs_manual_reconciliation") is True

        db_result = await db_session.execute(select(Subscription).where(Subscription.id == subscription.id))
        refreshed = db_result.scalar_one()
        assert refreshed.status == "paused"
        assert "reconciliation" in refreshed.pause_reason.lower()

        # The subscription must not be picked up again by the due-subscriptions query -
        # re-processing it would charge the customer a second time for this period.
        due_result = await scheduler.process_due_subscriptions()
        assert not any(r["subscription_id"] == str(subscription.id) for r in due_result["results"])

    async def test_no_variants_fails_gracefully(self, db_session, test_user, subscription):
        subscription.variant_ids = []
        await db_session.commit()
        scheduler = SubscriptionScheduler(db_session)
        result = await scheduler.process_subscription(subscription.id)
        assert result["success"] is False
        assert "No products" in result["error"]

    async def test_variant_ids_pointing_to_nonexistent_variants_fails_gracefully(self, db_session, subscription):
        """variant_ids is a plain JSON list with no FK enforcement, so it can
        reference variants that were since deleted - process_subscription must
        report this rather than crashing on an empty query result."""
        subscription.variant_ids = [str(uuid4())]
        await db_session.commit()
        scheduler = SubscriptionScheduler(db_session)
        result = await scheduler.process_subscription(subscription.id)
        assert result["success"] is False
        assert "No valid variants" in result["error"]

    async def test_unknown_subscription_id_reports_not_found(self, db_session):
        scheduler = SubscriptionScheduler(db_session)
        result = await scheduler.process_subscription(uuid4())
        assert result["success"] is False
        assert "not found" in result["message"].lower()

    async def test_second_payment_failure_schedules_retry_in_24_hours(self, db_session, test_user, variant, subscription, mocker):
        mocker.patch(
            "services.commerce.payments.PaymentService.process_idempotent",
            return_value={"status": "failed", "error": "Card declined"},
        )
        pm = PaymentMethod(
            id=uuid7(), user_id=test_user.id, type=PaymentType.CARD, provider=PaymentProvider.STRIPE,
            last_four="0002", expiry_month=12, expiry_year=2099, brand=CardBrand.VISA,
            stripe_payment_method_id=f"pm_test_{uuid4().hex[:16]}", is_default=True, is_active=True,
        )
        db_session.add(pm)
        subscription.payment_retry_count = 1
        await db_session.commit()

        scheduler = SubscriptionScheduler(db_session)
        result = await scheduler.process_subscription(subscription.id)
        assert result["success"] is False
        assert result["retry_count"] == 2

        await db_session.refresh(subscription)
        assert subscription.status == "payment_failed"
        assert subscription.next_retry_date is not None
        hours_until_retry = (subscription.next_retry_date - datetime.now(timezone.utc)).total_seconds() / 3600
        assert 23.9 <= hours_until_retry <= 24.1

    async def test_pause_email_notification_failure_does_not_block_pausing(self, db_session, test_user, variant, subscription, mocker):
        """The 3rd-failure pause path tries to email the customer - if that
        email send itself blows up, the subscription must still end up paused
        rather than the whole request failing."""
        mocker.patch(
            "services.commerce.payments.PaymentService.process_idempotent",
            return_value={"status": "failed", "error": "Card declined"},
        )
        mocker.patch(
            "services.accounts.email.EmailService.send_subscription_payment_failed",
            side_effect=Exception("smtp unavailable"),
        )
        pm = PaymentMethod(
            id=uuid7(), user_id=test_user.id, type=PaymentType.CARD, provider=PaymentProvider.STRIPE,
            last_four="0002", expiry_month=12, expiry_year=2099, brand=CardBrand.VISA,
            stripe_payment_method_id=f"pm_test_{uuid4().hex[:16]}", is_default=True, is_active=True,
        )
        db_session.add(pm)
        subscription.payment_retry_count = 2
        await db_session.commit()

        scheduler = SubscriptionScheduler(db_session)
        result = await scheduler.process_subscription(subscription.id)
        assert result["success"] is False

        await db_session.refresh(subscription)
        assert subscription.status == "paused"


class TestProcessDueSubscriptions:

    async def test_processes_only_due_active_subscriptions(self, db_session, test_user, variant, payment_method, subscription):
        scheduler = SubscriptionScheduler(db_session)
        result = await scheduler.process_due_subscriptions()
        assert result["total_due"] >= 1
        assert any(r["subscription_id"] == str(subscription.id) for r in result["results"])

    async def test_not_yet_due_subscription_is_excluded(self, db_session, test_user, variant):
        service = SubscriptionService(db_session)
        future_sub = await service.create(user_id=test_user.id, name="Not Due", variant_ids=[str(variant.id)])
        future_sub_id = str(future_sub.id)  # read before process_due_subscriptions() may expire it
        scheduler = SubscriptionScheduler(db_session)
        result = await scheduler.process_due_subscriptions()
        assert not any(r["subscription_id"] == future_sub_id for r in result["results"])

    async def test_one_failure_does_not_crash_the_rest_of_the_batch(self, db_session, test_user, admin_user, variant, payment_method, subscription):
        """Regression test: process_subscription() used to receive a live
        Subscription object and read its attributes throughout. When an
        earlier subscription in this same loop failed, its own
        db.rollback() expired every attribute on every object already
        loaded in this shared session - including subscriptions not yet
        processed - so the very next subscription.status read crashed with
        MissingGreenlet (a synchronous lazy-reload with no async context)."""
        # admin_user has no payment method - a distinct owner from test_user (who does),
        # so this one is guaranteed to fail rather than also succeed.
        no_pm_sub = await SubscriptionService(db_session).create(
            user_id=admin_user.id, name="No Payment Method", variant_ids=[str(variant.id)]
        )
        no_pm_sub.next_billing_date = datetime.now(timezone.utc) - timedelta(hours=1)
        await db_session.commit()
        subscription_id, no_pm_sub_id = str(subscription.id), str(no_pm_sub.id)

        scheduler = SubscriptionScheduler(db_session)
        result = await scheduler.process_due_subscriptions()

        assert result["total_due"] >= 2
        by_id = {r["subscription_id"]: r for r in result["results"]}
        assert by_id[subscription_id]["status"] == "success"
        assert by_id[no_pm_sub_id]["status"] == "failed"

    async def test_an_unexpected_raise_from_process_subscription_is_caught_per_item(
        self, db_session, test_user, variant, payment_method, subscription, mocker
    ):
        """process_subscription() itself catches virtually everything and returns
        a failure dict - but the batch loop in process_due_subscriptions() has its
        own safety net in case a subscription blows up in some way process_subscription
        can't turn into a dict (e.g. it raising directly). This is only reachable by
        forcing that failure mode directly."""
        mocker.patch.object(
            SubscriptionScheduler, "process_subscription", side_effect=Exception("totally unexpected"),
        )
        scheduler = SubscriptionScheduler(db_session)
        result = await scheduler.process_due_subscriptions()

        assert result["failed_count"] >= 1
        assert result["processed_count"] == 0
        entry = next(r for r in result["results"] if r["subscription_id"] == str(subscription.id))
        assert entry["status"] == "failed"
        assert "totally unexpected" in entry["reason"]


class TestGenerateOrderNumber:

    async def test_generates_sub_prefixed_number(self, db_session):
        scheduler = SubscriptionScheduler(db_session)
        number = await scheduler._generate_order_number()
        assert number.startswith("SUB-")


class TestGetShippingAddress:

    async def test_uses_delivery_address_when_set(self, db_session, test_user, subscription):
        address = Address(
            id=uuid7(), user_id=test_user.id, street="1 Test St", city="Lagos",
            state="Lagos", country="NG", post_code="100001",
        )
        db_session.add(address)
        subscription.delivery_address_id = address.id
        await db_session.commit()

        scheduler = SubscriptionScheduler(db_session)
        result = await scheduler._get_shipping_address(subscription)
        assert result["city"] == "Lagos"

    async def test_falls_back_when_no_address(self, db_session, subscription):
        subscription.delivery_address_id = None
        await db_session.commit()
        scheduler = SubscriptionScheduler(db_session)
        result = await scheduler._get_shipping_address(subscription)
        assert result["type"] == "shipping"
        assert "street" not in result


class TestUpdateBillingDates:

    async def test_monthly_advances_one_month(self, db_session, subscription):
        subscription.billing_cycle = "monthly"
        subscription.current_period_end = datetime(2026, 1, 31, tzinfo=timezone.utc)
        scheduler = SubscriptionScheduler(db_session)
        await scheduler._update_billing_dates(subscription)
        # Jan 31 + 1 month lands on the last day of Feb (leap year handling via relativedelta)
        assert subscription.current_period_end.month == 2

    async def test_weekly_advances_one_week(self, db_session, subscription):
        subscription.billing_cycle = "weekly"
        start = datetime.now(timezone.utc)
        subscription.current_period_end = start
        scheduler = SubscriptionScheduler(db_session)
        await scheduler._update_billing_dates(subscription)
        assert (subscription.current_period_end - start).days == 7

    async def test_yearly_advances_one_year(self, db_session, subscription):
        subscription.billing_cycle = "yearly"
        subscription.current_period_end = datetime(2026, 3, 1, tzinfo=timezone.utc)
        scheduler = SubscriptionScheduler(db_session)
        await scheduler._update_billing_dates(subscription)
        assert subscription.current_period_end.year == 2027

    async def test_tracks_orders_created_count(self, db_session, subscription):
        subscription.subscription_metadata = {"orders_created_count": 2}
        scheduler = SubscriptionScheduler(db_session)
        await scheduler._update_billing_dates(subscription)
        assert subscription.subscription_metadata["orders_created_count"] == 3


class TestProcessSubscriptionShipmentsTask:
    """Tests for the standalone process_subscription_shipments() background-task
    wrapper, which pulls its own session from core.db.get_db() rather than
    receiving one - substitute get_db with a fake generator yielding the test's
    own db_session so it runs against the real, rolled-back-at-teardown DB."""

    async def test_runs_the_scheduler_and_returns_its_result(self, db_session, test_user, variant, payment_method, subscription, mocker):
        async def fake_get_db():
            yield db_session
        mocker.patch("services.commerce.subscriptions_scheduler.get_db", fake_get_db)

        result = await process_subscription_shipments()
        assert result["total_due"] >= 1

    async def test_propagates_and_logs_scheduler_failure(self, db_session, mocker):
        async def fake_get_db():
            yield db_session
        mocker.patch("services.commerce.subscriptions_scheduler.get_db", fake_get_db)
        mocker.patch.object(
            SubscriptionScheduler, "process_due_subscriptions",
            side_effect=Exception("scheduler blew up"),
        )

        with pytest.raises(Exception, match="scheduler blew up"):
            await process_subscription_shipments()
