"""Tests for models/accounts/analytics.py - UserSession, CustomerLifecycleMetrics."""

from datetime import datetime, timezone

from core.utils.uuid_utils import uuid7
from models.accounts.analytics import UserSession, CustomerLifecycleMetrics, TrafficSource


class TestUserSessionToDict:

    def test_serializes_traffic_source_and_core_fields(self):
        session = UserSession(
            id=uuid7(), session_id="sess-123", user_id=uuid7(),
            device_type="mobile", browser="Safari", os="iOS",
            traffic_source=TrafficSource.PAID_SEARCH,
            started_at=datetime.now(timezone.utc), page_views=3, events_count=5, converted=True,
        )
        data = session.to_dict()
        assert data["traffic_source"] == "paid_search"
        assert data["session_id"] == "sess-123"
        assert data["converted"] is True

    def test_handles_no_user_and_no_traffic_source(self):
        session = UserSession(id=uuid7(), session_id="sess-456", user_id=None, traffic_source=None)
        data = session.to_dict()
        assert data["user_id"] is None
        assert data["traffic_source"] is None


class TestCustomerLifecycleMetricsToDict:

    def test_serializes_purchase_and_engagement_metrics(self):
        metrics = CustomerLifecycleMetrics(
            id=uuid7(), user_id=uuid7(), registered_at=datetime.now(timezone.utc),
            total_orders=4, total_revenue=199.96, average_order_value=49.99,
            customer_segment="loyal", lifetime_value=199.96,
        )
        data = metrics.to_dict()
        assert data["total_orders"] == 4
        assert data["customer_segment"] == "loyal"
        assert data["first_purchase_at"] is None
