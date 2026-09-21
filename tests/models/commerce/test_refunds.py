"""Tests for models/commerce/refunds.py - Refund, RefundItem."""

from datetime import datetime, timedelta, timezone

from core.utils.uuid_utils import uuid7
from models.commerce.refunds import Refund, RefundItem, RefundStatus, RefundReason, RefundType
from models.commerce.orders import Order


def make_refund(order_created_days_ago=1, reason=RefundReason.DEFECTIVE_PRODUCT,
                 amount=100.0, refund_type=RefundType.FULL_REFUND) -> Refund:
    refund = Refund(
        id=uuid7(), order_id=uuid7(), user_id=uuid7(), refund_number="REF-00000001",
        status=RefundStatus.REQUESTED, refund_type=refund_type, reason=reason,
        requested_amount=amount, currency="USD",
    )
    # is_eligible_for_auto_approval only reads order.created_at - a real
    # (unpersisted) Order instance, since the relationship setter below
    # requires a proper mapped object, not a plain namespace.
    refund.order = Order(
        id=uuid7(), order_number="ORD-TEST", user_id=uuid7(),
        subtotal=amount, total_amount=amount, billing_address={}, shipping_address={},
        created_at=datetime.now(timezone.utc) - timedelta(days=order_created_days_ago),
    )
    return refund


class TestRefundToDict:

    def test_serializes_enum_fields_as_values(self):
        refund = make_refund()
        data = refund.to_dict()
        assert data["status"] == "requested"
        assert data["reason"] == "defective_product"
        assert data["refund_type"] == "full_refund"

    def test_null_timestamps_serialize_as_none(self):
        refund = make_refund()
        data = refund.to_dict()
        assert data["approved_at"] is None
        assert data["completed_at"] is None


class TestIsEligibleForAutoApproval:

    def test_eligible_defective_product_within_window(self):
        refund = make_refund(order_created_days_ago=5, reason=RefundReason.DEFECTIVE_PRODUCT, amount=100.0)
        assert refund.is_eligible_for_auto_approval is True

    def test_ineligible_reason_not_in_whitelist(self):
        refund = make_refund(reason=RefundReason.CHANGED_MIND)
        assert refund.is_eligible_for_auto_approval is False

    def test_ineligible_when_order_too_old(self):
        refund = make_refund(order_created_days_ago=31, reason=RefundReason.DEFECTIVE_PRODUCT)
        assert refund.is_eligible_for_auto_approval is False

    def test_eligible_at_exactly_30_days(self):
        refund = make_refund(order_created_days_ago=30, reason=RefundReason.DEFECTIVE_PRODUCT)
        assert refund.is_eligible_for_auto_approval is True

    def test_ineligible_when_amount_exceeds_500(self):
        refund = make_refund(reason=RefundReason.DEFECTIVE_PRODUCT, amount=500.01)
        assert refund.is_eligible_for_auto_approval is False

    def test_eligible_at_exactly_500(self):
        refund = make_refund(reason=RefundReason.DEFECTIVE_PRODUCT, amount=500.00)
        assert refund.is_eligible_for_auto_approval is True

    def test_ineligible_for_partial_refund(self):
        refund = make_refund(reason=RefundReason.DEFECTIVE_PRODUCT, refund_type=RefundType.PARTIAL_REFUND)
        assert refund.is_eligible_for_auto_approval is False

    def test_ineligible_when_order_missing(self):
        refund = make_refund()
        refund.order = None
        assert refund.is_eligible_for_auto_approval is False

    def test_all_whitelisted_reasons_are_eligible(self):
        for reason in [
            RefundReason.DEFECTIVE_PRODUCT, RefundReason.WRONG_ITEM,
            RefundReason.DAMAGED_IN_SHIPPING, RefundReason.MISSING_PARTS,
        ]:
            refund = make_refund(reason=reason)
            assert refund.is_eligible_for_auto_approval is True, reason


class TestRefundItemToDict:

    def test_serializes_fields(self):
        item = RefundItem(
            id=uuid7(), refund_id=uuid7(), order_item_id=uuid7(),
            quantity_to_refund=2, unit_price=19.99, total_refund_amount=39.98,
        )
        data = item.to_dict()
        assert data["quantity_to_refund"] == 2
        assert data["total_refund_amount"] == 39.98
