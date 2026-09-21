"""Tests for models/system/analytics.py - AnalyticsEvent, ConversionFunnel."""

from datetime import datetime, timezone

from core.utils.uuid_utils import uuid7
from models.system.analytics import AnalyticsEvent, ConversionFunnel, EventType


class TestAnalyticsEventToDict:

    def test_serializes_event_type_and_financial_data(self):
        event = AnalyticsEvent(
            id=uuid7(), session_id="sess-123", user_id=uuid7(), event_type=EventType.PURCHASE,
            order_id=uuid7(), revenue=49.99, quantity=2,
            timestamp=datetime.now(timezone.utc),
        )
        data = event.to_dict()
        assert data["event_type"] == "purchase"
        assert data["revenue"] == 49.99
        assert data["quantity"] == 2

    def test_handles_no_event_type_and_no_optional_ids(self):
        event = AnalyticsEvent(id=uuid7(), session_id="sess-456", user_id=None, event_type=None)
        data = event.to_dict()
        assert data["event_type"] is None
        assert data["user_id"] is None
        assert data["order_id"] is None


class TestConversionFunnelFields:

    def test_stores_step_progress_and_values(self):
        funnel = ConversionFunnel(
            id=uuid7(), session_id="sess-123", user_id=uuid7(),
            current_step=2, max_step_reached=3, completed=False,
            cart_value=99.98, purchase_value=None,
        )
        assert funnel.current_step == 2
        assert funnel.max_step_reached == 3
        assert funnel.completed is False
        assert funnel.cart_value == 99.98
