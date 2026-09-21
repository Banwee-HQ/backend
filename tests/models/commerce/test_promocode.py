"""Tests for models/commerce/promocode.py - Promocode.

No to_dict()/properties on this model - just field storage worth pinning.
"""

from decimal import Decimal

from core.utils.uuid_utils import uuid7
from models.commerce.promocode import Promocode, DiscountType


class TestPromocodeFields:

    def test_stores_percentage_discount(self):
        promo = Promocode(id=uuid7(), code="SAVE10", discount_type=DiscountType.PERCENTAGE.value, value=Decimal("10.00"))
        assert promo.code == "SAVE10"
        assert promo.discount_type == "percentage"
        assert promo.value == Decimal("10.00")

    def test_stores_fixed_discount_with_caps(self):
        promo = Promocode(
            id=uuid7(), code="FLAT5", discount_type=DiscountType.FIXED.value, value=Decimal("5.00"),
            minimum_order_amount=Decimal("20.00"), maximum_discount_amount=Decimal("5.00"),
        )
        assert promo.minimum_order_amount == Decimal("20.00")
        assert promo.maximum_discount_amount == Decimal("5.00")
