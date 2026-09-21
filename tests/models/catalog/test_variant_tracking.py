"""Tests for models/catalog/variant_tracking.py."""

from decimal import Decimal
from datetime import datetime, timezone

from core.utils.uuid_utils import uuid7
from models.catalog.variant_tracking import (
    VariantTrackingEntry, VariantPriceHistory, VariantAnalytics, VariantSubstitution,
    TrackingActionType, AnalyticsPeriodType,
)


class TestVariantTrackingEntryToDict:

    def test_serializes_action_type_and_price(self):
        entry = VariantTrackingEntry(
            id=uuid7(), variant_id=uuid7(), subscription_id=uuid7(),
            price_at_time=Decimal("19.99"), currency="USD", action_type=TrackingActionType.ADDED,
            tracking_timestamp=datetime.now(timezone.utc),
        )
        data = entry.to_dict()
        assert data["action_type"] == TrackingActionType.ADDED
        assert data["price_at_time"] == Decimal("19.99")


class TestVariantPriceHistoryToDict:

    def test_serializes_old_and_new_price(self):
        history = VariantPriceHistory(
            id=uuid7(), variant_id=uuid7(), old_price=Decimal("19.99"), new_price=Decimal("24.99"),
            currency="USD", effective_date=datetime.now(timezone.utc),
        )
        data = history.to_dict()
        assert data["old_price"] == Decimal("19.99")
        assert data["new_price"] == Decimal("24.99")
        assert data["changed_by_user_id"] is None


class TestVariantAnalyticsToDict:

    def test_serializes_metrics(self):
        analytics = VariantAnalytics(
            id=uuid7(), variant_id=uuid7(), date=datetime.now(timezone.utc),
            period_type=AnalyticsPeriodType.DAILY, total_subscriptions=5, total_revenue=Decimal("99.95"),
        )
        data = analytics.to_dict()
        assert data["period_type"] == AnalyticsPeriodType.DAILY
        assert data["total_subscriptions"] == 5


class TestVariantSubstitutionToDict:

    def test_serializes_similarity_and_usage(self):
        sub = VariantSubstitution(
            id=uuid7(), original_variant_id=uuid7(), substitute_variant_id=uuid7(),
            similarity_score=Decimal("0.85"), times_suggested=10, times_accepted=6,
            acceptance_rate=Decimal("0.6000"), is_active=True,
        )
        data = sub.to_dict()
        assert data["similarity_score"] == Decimal("0.85")
        assert data["acceptance_rate"] == Decimal("0.6000")
