"""Tests for models/commerce/discounts.py."""

from decimal import Decimal
from datetime import datetime, timedelta, timezone

from core.utils.uuid_utils import uuid7
from models.commerce.discounts import Discount, SubscriptionDiscount, ProductRemovalAudit, DiscountType


def make_discount(**overrides) -> Discount:
    fields = dict(
        id=uuid7(), code="SAVE10", type=DiscountType.PERCENTAGE.value, value=Decimal("10.00"),
        valid_from=datetime.now(timezone.utc) - timedelta(days=1),
        valid_until=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=True,
    )
    fields.update(overrides)
    return Discount(**fields)


class TestDiscountToDict:

    def test_serializes_core_fields(self):
        discount = make_discount()
        data = discount.to_dict()
        assert data["code"] == "SAVE10"
        assert data["type"] == "percentage"
        assert data["value"] == Decimal("10.00")

    def test_null_maximum_discount_serializes_as_none(self):
        discount = make_discount()
        assert discount.to_dict()["maximum_discount"] is None


class TestSubscriptionDiscountToDict:

    def test_includes_nested_discount_dict_when_present(self):
        discount = make_discount()
        sub_discount = SubscriptionDiscount(
            id=uuid7(), subscription_id=uuid7(), discount_id=discount.id,
            discount_amount=Decimal("5.00"), applied_at=datetime.now(timezone.utc),
        )
        sub_discount.discount = discount
        data = sub_discount.to_dict()
        assert data["discount_amount"] == Decimal("5.00")
        assert data["discount"]["code"] == "SAVE10"

    def test_null_discount_relationship_serializes_as_none(self):
        sub_discount = SubscriptionDiscount(
            id=uuid7(), subscription_id=uuid7(), discount_id=uuid7(),
            discount_amount=Decimal("5.00"), applied_at=datetime.now(timezone.utc),
        )
        assert sub_discount.to_dict()["discount"] is None


class TestProductRemovalAuditToDict:

    def test_serializes_fields(self):
        audit = ProductRemovalAudit(
            id=uuid7(), subscription_id=uuid7(), product_id=uuid7(), removed_by=uuid7(),
            removed_at=datetime.now(timezone.utc), reason="Customer request",
        )
        data = audit.to_dict()
        assert data["reason"] == "Customer request"
        assert data["removed_by"] == str(audit.removed_by)
