"""Tests for models/commerce/payments.py - PaymentMethod, PaymentIntent, Transaction, PaymentAnalytics."""

from datetime import datetime, date, timezone
from decimal import Decimal

from core.utils.uuid_utils import uuid7
from models.commerce.payments import (
    PaymentMethod, PaymentIntent, Transaction, PaymentAnalytics,
    PaymentType, PaymentProvider, CardBrand, TransactionType,
)


class TestPaymentMethodToDict:

    def test_serializes_enum_fields_as_values(self):
        pm = PaymentMethod(
            id=uuid7(), user_id=uuid7(), type=PaymentType.CARD, provider=PaymentProvider.STRIPE,
            brand=CardBrand.VISA, last_four="4242", is_default=True, is_active=True,
        )
        data = pm.to_dict()
        assert data["type"] == "card"
        assert data["provider"] == "stripe"
        assert data["brand"] == "visa"

    def test_null_brand_serializes_as_none(self):
        pm = PaymentMethod(id=uuid7(), user_id=uuid7(), type=PaymentType.BANK_ACCOUNT, provider=PaymentProvider.STRIPE)
        assert pm.to_dict()["brand"] is None


class TestPaymentIntentAmount:

    def test_reads_total_from_amount_breakdown(self):
        intent = PaymentIntent(
            id=uuid7(), stripe_payment_intent_id="pi_123", user_id=uuid7(),
            amount_breakdown={"total": 49.98, "currency": "USD"}, currency="USD",
        )
        assert intent.amount == 49.98

    def test_missing_total_key_defaults_to_zero(self):
        intent = PaymentIntent(
            id=uuid7(), stripe_payment_intent_id="pi_123", user_id=uuid7(),
            amount_breakdown={"currency": "USD"}, currency="USD",
        )
        assert intent.amount == 0.0

    def test_non_dict_breakdown_defaults_to_zero(self):
        intent = PaymentIntent(
            id=uuid7(), stripe_payment_intent_id="pi_123", user_id=uuid7(),
            amount_breakdown=None, currency="USD",
        )
        assert intent.amount == 0.0


class TestPaymentIntentToDict:

    def test_serializes_metadata_under_metadata_key(self):
        intent = PaymentIntent(
            id=uuid7(), stripe_payment_intent_id="pi_123", user_id=uuid7(),
            amount_breakdown={"total": 10.0}, currency="USD", status="succeeded",
            payment_intent_metadata={"request_id": "abc"},
        )
        data = intent.to_dict()
        assert data["metadata"] == {"request_id": "abc"}

    def test_null_order_id_serializes_as_none(self):
        intent = PaymentIntent(
            id=uuid7(), stripe_payment_intent_id="pi_123", user_id=uuid7(),
            amount_breakdown={"total": 10.0}, currency="USD", status="succeeded", order_id=None,
        )
        assert intent.to_dict()["order_id"] is None

    def test_set_order_id_serializes_as_string(self):
        order_id = uuid7()
        intent = PaymentIntent(
            id=uuid7(), stripe_payment_intent_id="pi_123", user_id=uuid7(),
            amount_breakdown={"total": 10.0}, currency="USD", status="succeeded", order_id=order_id,
        )
        assert intent.to_dict()["order_id"] == str(order_id)


class TestTransactionToDict:

    def test_serializes_amount_and_metadata(self):
        txn = Transaction(
            id=uuid7(), user_id=uuid7(), amount=Decimal("49.98"), currency="USD",
            status="succeeded", transaction_type=TransactionType.PAYMENT,
            transaction_metadata='{"stripe_request_id": "req_1"}',
        )
        data = txn.to_dict()
        assert data["amount"] == Decimal("49.98")
        assert data["metadata"] == '{"stripe_request_id": "req_1"}'

    def test_null_payment_intent_id_serializes_as_none(self):
        txn = Transaction(
            id=uuid7(), user_id=uuid7(), amount=Decimal("10.00"), currency="USD",
            status="pending", transaction_type=TransactionType.REFUND,
        )
        assert txn.to_dict()["payment_intent_id"] is None


class TestPaymentAnalyticsToDict:

    def test_serializes_date_and_breakdowns(self):
        analytics = PaymentAnalytics(
            id=uuid7(), date=date(2026, 1, 1), total_payments=10, successful_payments=8,
            failed_payments=2, pending_payments=0, success_rate=Decimal("0.8000"),
            total_volume=Decimal("500.00"), successful_volume=Decimal("400.00"),
            average_payment_amount=Decimal("50.00"), currency="USD",
            breakdown_by_method={"card": 8}, failure_breakdown={"card_declined": 2},
        )
        data = analytics.to_dict()
        assert data["date"] == "2026-01-01"
        assert data["breakdown_by_method"] == {"card": 8}
        assert data["failure_breakdown"] == {"card_declined": 2}

    def test_null_date_serializes_as_none(self):
        analytics = PaymentAnalytics(id=uuid7(), date=None)
        assert analytics.to_dict()["date"] is None
