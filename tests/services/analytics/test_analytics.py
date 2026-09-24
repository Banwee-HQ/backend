"""Tests for services/analytics/analytics.py - AnalyticsService."""

import pytest
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from fastapi import HTTPException

from core.utils.uuid_utils import uuid7
from services.analytics.analytics import AnalyticsService
from models.system.analytics import AnalyticsEvent, ConversionFunnel, EventType
from models.accounts.analytics import UserSession
from models.commerce.orders import Order, OrderItem, OrderStatus, PaymentStatus, FulfillmentStatus
from models.commerce.refunds import Refund, RefundStatus, RefundReason, RefundType
from models.commerce.subscriptions import Subscription
from models.catalog.category import Category
from models.catalog.product import Product, ProductVariant, ProductStatus
from models.catalog.inventories import Inventory


@pytest.fixture
async def category(db_session) -> Category:
    c = Category(id=uuid7(), name="Cat", slug=f"cat-{uuid4().hex[:8]}")
    db_session.add(c)
    await db_session.flush()
    return c


@pytest.fixture
async def variant(db_session, category) -> ProductVariant:
    product = Product(id=uuid7(), name="Widget", slug=f"widget-{uuid4().hex[:8]}", category_id=category.id)
    v = ProductVariant(id=uuid7(), product_id=product.id, sku=f"SKU-{uuid4().hex[:8]}", name="Default", base_price=Decimal("19.99"))
    db_session.add_all([product, v])
    await db_session.flush()
    db_session.add(Inventory(id=uuid7(), variant_id=v.id, quantity_available=50))
    await db_session.commit()
    return v


def make_order(user_id, status=OrderStatus.DELIVERED, total=Decimal("49.98"), created_at=None) -> Order:
    return Order(
        id=uuid7(), order_number=f"ORD-{uuid4().hex[:10].upper()}", user_id=user_id,
        order_status=status, payment_status=PaymentStatus.PAID, fulfillment_status=FulfillmentStatus.FULFILLED,
        subtotal=total, shipping_cost=Decimal("0.00"), tax_amount=Decimal("0.00"), total_amount=total,
        billing_address={}, shipping_address={},
        created_at=created_at or datetime.now(timezone.utc),
    )


@pytest.fixture
async def order(db_session, test_user) -> Order:
    o = make_order(test_user.id)
    db_session.add(o)
    await db_session.commit()
    return o


class TestTrackEvent:

    async def test_creates_session_and_event(self, db_session, test_user):
        service = AnalyticsService(db_session)
        session_id = f"sess-{uuid4().hex[:12]}"
        event = await service.track_event(session_id=session_id, event_type=EventType.PAGE_VIEW, user_id=test_user.id)
        assert event.session_id == session_id
        assert event.event_type == EventType.PAGE_VIEW

    async def test_auto_generates_session_id_when_missing(self, db_session, test_user):
        service = AnalyticsService(db_session)
        event = await service.track_event(session_id="", event_type=EventType.PAGE_VIEW, user_id=test_user.id)
        assert event.session_id

    async def test_reuses_existing_session(self, db_session, test_user):
        service = AnalyticsService(db_session)
        session_id = f"sess-{uuid4().hex[:12]}"
        await service.track_event(session_id=session_id, event_type=EventType.PAGE_VIEW, user_id=test_user.id)
        await service.track_event(session_id=session_id, event_type=EventType.CART_ADD, user_id=test_user.id)

        result = await db_session.execute(
            select(UserSession).where(UserSession.session_id == session_id)
        )
        sessions = result.scalars().all()
        assert len(sessions) == 1

    async def test_purchase_event_marks_session_converted(self, db_session, test_user):
        service = AnalyticsService(db_session)
        session_id = f"sess-{uuid4().hex[:12]}"
        await service.track_event(session_id=session_id, event_type=EventType.PURCHASE, user_id=test_user.id, revenue=49.98)

        result = await db_session.execute(select(UserSession).where(UserSession.session_id == session_id))
        session = result.scalar_one()
        assert session.converted is True
        assert float(session.conversion_value) == 49.98


class TestGetRefundRateMetrics:

    async def test_computes_refund_rate_from_real_refunds(self, db_session, test_user, order):
        start = datetime.now(timezone.utc) - timedelta(seconds=1)
        refund = Refund(
            id=uuid7(), order_id=order.id, user_id=test_user.id, refund_number=f"REF-{uuid4().hex[:8]}",
            status=RefundStatus.COMPLETED, refund_type=RefundType.FULL_REFUND, reason=RefundReason.CHANGED_MIND,
            requested_amount=Decimal("49.98"), approved_amount=Decimal("49.98"), processed_amount=Decimal("49.98"),
            currency="USD",
        )
        db_session.add(refund)
        await db_session.commit()

        service = AnalyticsService(db_session)
        # A narrow window scoped to just this test - the shared test DB
        # accumulates real, committed rows from every other test run.
        end = datetime.now(timezone.utc) + timedelta(seconds=1)
        result = await service.get_refund_rate_metrics(start, end)
        assert result["overall"]["total_refunds"] == 1
        assert result["overall"]["total_refund_amount"] == pytest.approx(49.98)
        assert result["by_reason"][0]["reason"] == "changed_mind"

    async def test_no_refunds_returns_zero_rate(self, db_session, order):
        # Wide window + before/after delta, matching the pattern above - narrow windows can still catch a neighboring test's order when the full file runs and tests execute back-to-back within the same second.
        service = AnalyticsService(db_session)
        start = datetime.now(timezone.utc) - timedelta(days=1)
        end = datetime.now(timezone.utc) + timedelta(days=1)
        result = await service.get_refund_rate_metrics(start, end)
        # `order` has no associated refund, so total_refunds must still be
        # less than total_orders (i.e. it wasn't miscounted as a refund).
        assert result["overall"]["total_refunds"] < result["overall"]["total_orders"]


class TestGetComprehensiveDashboardData:

    async def test_bundles_all_metrics(self, db_session, order):
        service = AnalyticsService(db_session)
        start = datetime.now(timezone.utc) - timedelta(days=1)
        end = datetime.now(timezone.utc) + timedelta(days=1)
        result = await service.get_comprehensive_dashboard_data(start, end)
        assert set(["conversion", "cart_abandonment", "time_to_purchase", "refunds", "repeat_customers"]) <= set(result.keys())


class TestUpdateConversionFunnel:

    async def test_creates_and_advances_funnel(self, db_session, test_user):
        # ConversionFunnel.session_id has a real FK to user_sessions.session_id.
        session_id = f"sess-{uuid4().hex[:12]}"
        db_session.add(UserSession(id=uuid7(), session_id=session_id, user_id=test_user.id, started_at=datetime.now(timezone.utc)))
        await db_session.flush()

        service = AnalyticsService(db_session)
        await service._update_conversion_funnel(session_id, test_user.id, EventType.PAGE_VIEW)
        # Flush between calls - real usage (via track_event()) commits after each
        # one, so without this both calls would miss the row and double-insert.
        await db_session.flush()
        await service._update_conversion_funnel(session_id, test_user.id, EventType.CART_ADD)
        await db_session.commit()

        result = await db_session.execute(select(ConversionFunnel).where(ConversionFunnel.session_id == session_id))
        funnel = result.scalar_one()
        assert funnel.current_step == 2
        assert funnel.landing_at is not None
        assert funnel.cart_add_at is not None

    async def test_checkout_start_advances_funnel_to_step_three(self, db_session, test_user):
        session_id = f"sess-{uuid4().hex[:12]}"
        db_session.add(UserSession(id=uuid7(), session_id=session_id, user_id=test_user.id, started_at=datetime.now(timezone.utc)))
        await db_session.flush()

        service = AnalyticsService(db_session)
        await service._update_conversion_funnel(session_id, test_user.id, EventType.CHECKOUT_START)
        await db_session.commit()

        result = await db_session.execute(select(ConversionFunnel).where(ConversionFunnel.session_id == session_id))
        funnel = result.scalar_one()
        assert funnel.current_step == 3
        assert funnel.checkout_start_at is not None

    async def test_purchase_marks_funnel_completed(self, db_session, test_user):
        session_id = f"sess-{uuid4().hex[:12]}"
        db_session.add(UserSession(id=uuid7(), session_id=session_id, user_id=test_user.id, started_at=datetime.now(timezone.utc)))
        await db_session.flush()

        service = AnalyticsService(db_session)
        await service._update_conversion_funnel(session_id, test_user.id, EventType.PURCHASE)
        await db_session.commit()

        result = await db_session.execute(select(ConversionFunnel).where(ConversionFunnel.session_id == session_id))
        funnel = result.scalar_one()
        assert funnel.completed is True
        assert funnel.current_step == 4


class TestGetUsersGrowthTrend:

    async def test_counts_new_users_excluding_admins(self, db_session, test_user):
        service = AnalyticsService(db_session)
        start = datetime.now(timezone.utc) - timedelta(days=1)
        end = datetime.now(timezone.utc) + timedelta(days=1)
        result = await service.get_users_growth_trend(start, end)
        assert result["total_new_users"] >= 1


class TestGetSalesTrendData:

    async def test_aggregates_daily_sales(self, db_session, order):
        service = AnalyticsService(db_session)
        start = datetime.now(timezone.utc) - timedelta(days=1)
        end = datetime.now(timezone.utc) + timedelta(days=1)
        result = await service.get_sales_trend_data(start, end)
        assert result["summary"]["total_orders"] >= 1
        assert result["summary"]["total_revenue"] >= 49.98

    async def test_growth_rate_computed_across_multiple_days(self, db_session, test_user):
        two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
        today = datetime.now(timezone.utc)
        db_session.add_all([
            make_order(test_user.id, total=Decimal("50.00"), created_at=two_days_ago),
            make_order(test_user.id, total=Decimal("100.00"), created_at=today),
        ])
        await db_session.commit()

        service = AnalyticsService(db_session)
        start = two_days_ago - timedelta(hours=1)
        end = today + timedelta(hours=1)
        result = await service.get_sales_trend_data(start, end)
        assert len(result["sales_trend"]) >= 2
        assert result["summary"]["growth_rate"] != 0.0


class TestGetRevenueMetrics:

    async def test_computes_revenue_from_completed_orders(self, db_session, test_user):
        order = make_order(test_user.id, status=OrderStatus.SHIPPED)
        db_session.add(order)
        await db_session.commit()

        service = AnalyticsService(db_session)
        start = datetime.now(timezone.utc) - timedelta(days=1)
        end = datetime.now(timezone.utc) + timedelta(days=1)
        result = await service.get_revenue_metrics(start, end)
        assert result["summary"]["completed_orders"] >= 1
        assert result["summary"]["total_revenue"] >= 49.98

    async def test_pending_orders_are_excluded(self, db_session, test_user):
        # A wide, shared window plus a before/after delta instead of an absolute
        # count, since the shared test DB has other committed orders too.
        service = AnalyticsService(db_session)
        start = datetime.now(timezone.utc) - timedelta(days=1)
        end = datetime.now(timezone.utc) + timedelta(days=1)
        before = (await service.get_revenue_metrics(start, end))["summary"]["completed_orders"]

        order = make_order(test_user.id, status=OrderStatus.PENDING)
        db_session.add(order)
        await db_session.commit()

        after = (await service.get_revenue_metrics(start, end))["summary"]["completed_orders"]
        assert after == before


class TestGetAdminStats:

    async def test_returns_full_shape(self, db_session, order):
        service = AnalyticsService(db_session)
        result = await service.get_admin_stats()
        assert "users" in result and "orders" in result and "revenue" in result

    async def test_status_filter_narrows_orders(self, db_session, order):
        service = AnalyticsService(db_session)
        result = await service.get_admin_stats(status="DELIVERED")
        assert result["orders"]["total"] >= 1

    async def test_category_filter_narrows_products(self, db_session, category):
        service = AnalyticsService(db_session)
        result = await service.get_admin_stats(category=category.slug)
        assert "products" in result


class TestGetAdminOverview:

    async def test_returns_platform_overview(self, db_session, order, variant):
        service = AnalyticsService(db_session)
        result = await service.get_admin_overview()
        assert "platform_overview" in result
        assert result["platform_overview"]["total_orders"] >= 1

    async def test_active_products_counts_active_status_products(self, db_session, variant):
        """Regression test: this compared Product.product_status == "active"
        (lowercase), but the column is a native Postgres enum that stores
        the enum member's uppercase name ("ACTIVE") - active_products was
        always 0 regardless of how many products were actually active."""
        service = AnalyticsService(db_session)
        result = await service.get_admin_overview()
        assert result["platform_overview"]["active_products"] >= 1

    async def test_db_error_is_wrapped_as_http_exception(self, db_session, mocker):
        service = AnalyticsService(db_session)
        mocker.patch.object(db_session, "scalar", side_effect=RuntimeError("boom"))
        with pytest.raises(HTTPException) as exc_info:
            await service.get_admin_overview()
        assert exc_info.value.status_code == 500


class TestTrackEventErrors:

    async def test_fk_violation_on_order_id_rolls_back_and_reraises(self, db_session, test_user):
        """order_id has a real FK to commerce.orders.id - a random UUID that isn't a
        real order fails at the DB level. track_event() must roll back and re-raise
        rather than swallow it."""
        service = AnalyticsService(db_session)
        with pytest.raises(Exception):
            await service.track_event(
                session_id=f"sess-{uuid4().hex[:12]}",
                event_type=EventType.PAGE_VIEW,
                user_id=test_user.id,
                order_id=uuid4(),
            )


class TestServiceMethodsWrapDbErrors:
    """Passing a non-datetime start_date makes every one of these fail at the DB
    driver level (it can't adapt the value for a timestamptz comparison) - a real,
    unmocked error that each method's try/except must translate into a clean
    HTTPException(500) instead of leaking a raw driver exception."""

    async def test_refund_rate_metrics(self, db_session):
        service = AnalyticsService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.get_refund_rate_metrics("not-a-date", "not-a-date")
        assert exc_info.value.status_code == 500

    async def test_comprehensive_dashboard_data_wraps_downstream_failure(self, db_session):
        service = AnalyticsService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.get_comprehensive_dashboard_data("not-a-date", "not-a-date")
        assert "dashboard data" in exc_info.value.detail

    async def test_users_growth_trend(self, db_session):
        service = AnalyticsService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.get_users_growth_trend("not-a-date", "not-a-date")
        assert exc_info.value.status_code == 500

    async def test_sales_trend_data(self, db_session):
        service = AnalyticsService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.get_sales_trend_data("not-a-date", "not-a-date")
        assert exc_info.value.status_code == 500

    async def test_revenue_metrics(self, db_session):
        service = AnalyticsService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.get_revenue_metrics("not-a-date", "not-a-date")
        assert exc_info.value.status_code == 500


class TestUpdateSessionMetricsErrors:

    async def test_db_error_is_logged_and_swallowed(self, db_session, mocker):
        """_update_session_metrics() is a best-effort side-channel update called from
        inside track_event() - a failure here must not blow up event tracking."""
        service = AnalyticsService(db_session)
        mocker.patch.object(db_session, "execute", side_effect=RuntimeError("boom"))
        await service._update_session_metrics("some-session-id")  # must not raise


class TestUpdateConversionFunnelErrors:

    async def test_db_error_is_logged_and_swallowed(self, db_session, test_user, mocker):
        service = AnalyticsService(db_session)
        mocker.patch.object(db_session, "execute", side_effect=RuntimeError("boom"))
        await service._update_conversion_funnel("sess-x", test_user.id, EventType.PAGE_VIEW)  # must not raise


class TestGetAdminStatsErrorPaths:

    async def test_malformed_date_from_falls_back_to_default_window(self, db_session, order):
        service = AnalyticsService(db_session)
        result = await service.get_admin_stats(date_from="not-a-date")
        assert "users" in result

    async def test_malformed_date_to_falls_back_to_default_window(self, db_session, order):
        service = AnalyticsService(db_session)
        result = await service.get_admin_stats(date_to="not-a-date")
        assert "users" in result

    async def test_unrecognized_status_value_is_ignored_not_raised(self, db_session, order):
        """OrderStatus(status.lower()) raises ValueError for a status string that isn't
        a real order status - the filter is skipped rather than the request failing."""
        service = AnalyticsService(db_session)
        result = await service.get_admin_stats(status="not_a_real_status")
        assert result["orders"]["total"] >= 1

    async def test_db_error_is_wrapped_as_http_exception(self, db_session, mocker):
        service = AnalyticsService(db_session)
        mocker.patch.object(db_session, "scalar", side_effect=RuntimeError("boom"))
        with pytest.raises(HTTPException) as exc_info:
            await service.get_admin_stats()
        assert exc_info.value.status_code == 500


def isolated_window():
    """A unique future day, so rows other tests committed to the shared DB never fall inside it."""
    day = datetime(2031, 1, 1, tzinfo=timezone.utc) + timedelta(days=uuid4().int % 3000, minutes=uuid4().int % 1000)
    return day, day + timedelta(hours=1)


async def add_session(db_session, source, started_at, events, user_id=None, revenue=None):
    from models.accounts.analytics import TrafficSource
    session_id = f"sess-{uuid4().hex}"
    db_session.add(UserSession(id=uuid7(), session_id=session_id, traffic_source=TrafficSource(source), started_at=started_at, user_id=user_id))
    await db_session.flush()
    for event_type, product_id in events:
        db_session.add(AnalyticsEvent(
            id=uuid7(), session_id=session_id, event_type=event_type, product_id=product_id, created_at=started_at,
            revenue=revenue if event_type == EventType.PURCHASE else None,
        ))
    await db_session.commit()


class TestSessionAttribution:

    async def test_first_event_records_traffic_source_and_utm(self, db_session):
        session_id = f"sess-{uuid4().hex}"
        await AnalyticsService(db_session).track_event(
            session_id=session_id, event_type=EventType.PAGE_VIEW,
            session_info={"traffic_source": "social", "referrer_url": "https://t.co/x", "utm_source": "twitter", "utm_campaign": "launch"},
        )
        session = (await db_session.execute(select(UserSession).where(UserSession.session_id == session_id))).scalar_one()
        assert session.traffic_source.value == "social"
        assert (session.utm_source, session.utm_campaign) == ("twitter", "launch")

    async def test_unknown_source_falls_back_to_direct(self, db_session):
        session_id = f"sess-{uuid4().hex}"
        await AnalyticsService(db_session).track_event(session_id=session_id, event_type=EventType.PAGE_VIEW, session_info={"traffic_source": "bogus"})
        session = (await db_session.execute(select(UserSession).where(UserSession.session_id == session_id))).scalar_one()
        assert session.traffic_source.value == "direct"


class TestConcurrentFirstEvents:

    async def test_second_insert_of_the_same_session_is_harmless(self, db_session):
        """Two events racing on a visitor's first page must both be recorded (no unique-key 500)."""
        service = AnalyticsService(db_session)
        session_id = f"sess-{uuid4().hex}"
        await service.track_event(session_id=session_id, event_type=EventType.PAGE_VIEW)
        await service.track_event(session_id=session_id, event_type=EventType.PAGE_VIEW, session_info={"traffic_source": "social"})
        sessions = (await db_session.execute(select(UserSession).where(UserSession.session_id == session_id))).scalars().all()
        events = (await db_session.execute(select(AnalyticsEvent).where(AnalyticsEvent.session_id == session_id))).scalars().all()
        assert len(sessions) == 1 and sessions[0].traffic_source.value == "direct"  # first event's attribution wins
        assert len(events) == 2


class TestConversionFromTrackedSessions:
    """Conversion and traffic sources come only from tracked sessions - nothing is extrapolated from orders."""

    async def test_counts_real_sessions_and_purchases(self, db_session, test_user):
        start, end = isolated_window()
        at = start + timedelta(minutes=5)
        await add_session(db_session, "organic_search", at, [(EventType.PAGE_VIEW, None), (EventType.PURCHASE, None)], revenue=Decimal("30.00"))
        await add_session(db_session, "organic_search", at, [(EventType.PAGE_VIEW, None)])
        await add_session(db_session, "paid_search", at, [(EventType.PAGE_VIEW, None)])

        result = await AnalyticsService(db_session).get_conversion_metrics(start, end)
        assert result["overall"]["total_sessions"] == 3
        assert result["overall"]["converted_sessions"] == 1
        assert result["overall"]["conversion_rate"] == pytest.approx(33.33)
        by_source = {row["traffic_source"]: row for row in result["by_traffic_source"]}
        assert by_source["organic_search"]["total_sessions"] == 2
        assert by_source["organic_search"]["conversion_rate"] == 50.0
        assert by_source["organic_search"]["revenue"] == 30.0
        assert by_source["paid_search"]["converted_sessions"] == 0

    async def test_no_traffic_means_no_sessions(self, db_session):
        start, end = isolated_window()
        result = await AnalyticsService(db_session).get_conversion_metrics(start, end)
        assert result["overall"]["total_sessions"] == 0
        assert result["by_traffic_source"] == []


class TestFunnelFromTrackedEvents:

    async def test_funnel_counts_distinct_sessions_per_step(self, db_session, variant):
        start, end = isolated_window()
        at = start + timedelta(minutes=5)
        pid = variant.product_id
        await add_session(db_session, "direct", at, [(EventType.PAGE_VIEW, None), (EventType.PAGE_VIEW, pid), (EventType.CART_ADD, pid),
                                                    (EventType.CHECKOUT_START, None), (EventType.PURCHASE, None)])
        await add_session(db_session, "direct", at, [(EventType.PAGE_VIEW, pid), (EventType.CART_ADD, pid), (EventType.CART_ADD, pid)])
        await add_session(db_session, "direct", at, [(EventType.PAGE_VIEW, None)])

        result = await AnalyticsService(db_session).get_cart_abandonment_metrics(start, end)
        counts = [step["count"] for step in result["conversion_funnel"]]
        assert counts == [3, 2, 2, 1, 1]
        assert result["abandonment_rates"]["cart_abandonment_rate"] == 50.0
        assert result["abandonment_rates"]["checkout_abandonment_rate"] == 0.0

    async def test_empty_period_is_all_zero(self, db_session):
        start, end = isolated_window()
        result = await AnalyticsService(db_session).get_cart_abandonment_metrics(start, end)
        assert [step["count"] for step in result["conversion_funnel"]] == [0, 0, 0, 0, 0]


class TestTimeToFirstPurchase:

    async def test_measures_signup_to_first_paid_order(self, db_session, test_user):
        start, end = isolated_window()
        test_user.created_at = start - timedelta(hours=48)
        db_session.add_all([
            make_order(test_user.id, created_at=start + timedelta(minutes=10)),
            make_order(test_user.id, created_at=start + timedelta(minutes=40)),  # not the first order
        ])
        await db_session.commit()

        result = await AnalyticsService(db_session).get_time_to_purchase_metrics(start, end)
        assert result["metrics"]["total_first_purchases"] == 1
        assert result["metrics"]["average_hours"] == pytest.approx(48.17, abs=0.01)
        assert {b["range"]: b["count"] for b in result["distribution"]}["1-7 days"] == 1

    async def test_empty_period_has_no_distribution(self, db_session):
        start, end = isolated_window()
        result = await AnalyticsService(db_session).get_time_to_purchase_metrics(start, end)
        assert result["metrics"]["total_first_purchases"] == 0
        assert result["distribution"] == []


class TestRepeatCustomers:

    async def test_segments_and_gaps_come_from_orders(self, db_session, test_user, admin_user):
        start, end = isolated_window()
        db_session.add_all([
            make_order(test_user.id, total=Decimal("10.00"), created_at=start + timedelta(minutes=0)),
            make_order(test_user.id, total=Decimal("20.00"), created_at=start + timedelta(minutes=30)),
            make_order(admin_user.id, total=Decimal("5.00"), created_at=start + timedelta(minutes=5)),
            make_order(admin_user.id, status=OrderStatus.PENDING, created_at=start + timedelta(minutes=6)),  # unpaid: ignored
        ])
        await db_session.commit()

        result = await AnalyticsService(db_session).get_repeat_customer_metrics(start, end)
        assert result["overall"]["total_customers"] == 2
        assert result["overall"]["repeat_customers"] == 1
        assert result["overall"]["repeat_rate"] == 50.0
        segments = {seg["segment"]: seg for seg in result["by_segment"]}
        assert segments["new"]["count"] == 1 and segments["new"]["average_ltv"] == 5.0
        assert segments["returning"]["count"] == 1 and segments["returning"]["average_ltv"] == 30.0
        assert segments["loyal"]["count"] == 0
        assert {f["order_count"]: f["customer_count"] for f in result["frequency_distribution"]} == {1: 1, 2: 1, 3: 0, 4: 0}
