"""Tests for schemas/commerce/refunds.py - Request.validate_items."""

import pytest
from pydantic import ValidationError

from schemas.commerce.refunds import Request, ItemRequest
from models.commerce.refunds import RefundReason


class TestRequestValidateItems:

    def test_requires_at_least_one_item(self):
        with pytest.raises(ValidationError):
            Request(reason=RefundReason.DAMAGED_IN_SHIPPING, items=[])

    def test_accepts_valid_items(self):
        from uuid import uuid4
        request = Request(reason=RefundReason.DAMAGED_IN_SHIPPING, items=[ItemRequest(order_item_id=uuid4(), quantity=1)])
        assert len(request.items) == 1
