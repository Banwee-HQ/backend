"""Tests for schemas/commerce/transaction.py."""

import pytest
from pydantic import ValidationError

from schemas.commerce.transaction import TransactionBase


class TestTransactionBase:

    def test_requires_stripe_payment_intent_id(self):
        from uuid import uuid4
        with pytest.raises(ValidationError):
            TransactionBase(user_id=uuid4(), amount=10.0, currency="USD")

    def test_defaults_status_to_pending(self):
        from uuid import uuid4
        txn = TransactionBase(user_id=uuid4(), stripe_payment_intent_id="pi_1", amount=10.0, currency="USD")
        assert txn.status == "pending"
