"""Tests for services/commerce/discounts.py - DiscountEngine.calculate_discount_amount.

Pure calculation logic (no DB access), so it's tested directly against a
lightweight Discount instance rather than through the API or a real session.
"""

from decimal import Decimal
from types import SimpleNamespace

from services.commerce.discounts import DiscountEngine
from models.commerce.discounts import DiscountType


def make_discount(discount_type: str, value, maximum_discount=None, code="SAVE10"):
    return SimpleNamespace(type=discount_type, value=value, maximum_discount=maximum_discount, code=code)


class TestPercentageDiscount:

    async def test_applies_percentage_to_subtotal(self):
        engine = DiscountEngine(db=None)
        discount = make_discount(DiscountType.PERCENTAGE.value, 10)
        result = await engine.calculate_discount_amount(discount, subtotal=Decimal("100.00"))
        assert result["discount_amount"] == Decimal("10.00")
        assert result["final_total"] == Decimal("90.00")

    async def test_percentage_is_capped_by_maximum_discount(self):
        engine = DiscountEngine(db=None)
        discount = make_discount(DiscountType.PERCENTAGE.value, 50, maximum_discount=20)
        result = await engine.calculate_discount_amount(discount, subtotal=Decimal("1000.00"))
        assert result["discount_amount"] == Decimal("20")

    async def test_percentage_includes_shipping_and_tax_in_final_total(self):
        engine = DiscountEngine(db=None)
        discount = make_discount(DiscountType.PERCENTAGE.value, 10)
        result = await engine.calculate_discount_amount(
            discount, subtotal=Decimal("100.00"), shipping_cost=Decimal("10.00"), tax_amount=Decimal("5.00")
        )
        # 100 + 10 + 5 - 10 (10% of subtotal only)
        assert result["final_total"] == Decimal("105.00")


class TestFixedAmountDiscount:

    async def test_subtracts_the_fixed_value(self):
        engine = DiscountEngine(db=None)
        discount = make_discount(DiscountType.FIXED_AMOUNT.value, 15)
        result = await engine.calculate_discount_amount(discount, subtotal=Decimal("100.00"))
        assert result["discount_amount"] == Decimal("15")

    async def test_never_exceeds_the_subtotal(self):
        engine = DiscountEngine(db=None)
        discount = make_discount(DiscountType.FIXED_AMOUNT.value, 500)
        result = await engine.calculate_discount_amount(discount, subtotal=Decimal("50.00"))
        assert result["discount_amount"] == Decimal("50.00")
        assert result["final_total"] == Decimal("0")


class TestFreeShippingDiscount:

    async def test_discount_equals_shipping_cost(self):
        engine = DiscountEngine(db=None)
        discount = make_discount(DiscountType.FREE_SHIPPING.value, 0)
        result = await engine.calculate_discount_amount(
            discount, subtotal=Decimal("100.00"), shipping_cost=Decimal("12.00")
        )
        assert result["discount_amount"] == Decimal("12.00")
        assert result["final_total"] == Decimal("100.00")


class TestUnknownDiscountType:

    async def test_unknown_type_applies_no_discount_instead_of_raising(self):
        engine = DiscountEngine(db=None)
        discount = make_discount("not_a_real_type", 10)
        result = await engine.calculate_discount_amount(discount, subtotal=Decimal("100.00"))
        assert result["discount_amount"] == Decimal("0")
        assert result["final_total"] == Decimal("100.00")


class TestFinalTotalNeverNegative:

    async def test_discount_larger_than_everything_floors_at_zero(self):
        engine = DiscountEngine(db=None)
        discount = make_discount(DiscountType.FIXED_AMOUNT.value, 1000)
        result = await engine.calculate_discount_amount(discount, subtotal=Decimal("10.00"))
        assert result["final_total"] >= Decimal("0")


class TestCalculationErrorHandling:

    async def test_non_numeric_value_falls_back_to_no_discount_instead_of_raising(self):
        """A corrupt/non-numeric discount.value must not blow up checkout math -
        the method swallows it and charges the customer the full, undiscounted total."""
        engine = DiscountEngine(db=None)
        discount = make_discount(DiscountType.PERCENTAGE.value, "not-a-number")
        result = await engine.calculate_discount_amount(
            discount, subtotal=Decimal("100.00"), shipping_cost=Decimal("5.00"), tax_amount=Decimal("2.00")
        )
        assert result["discount_amount"] == Decimal("0")
        assert result["final_total"] == Decimal("107.00")
        assert result["discount_type"] == DiscountType.PERCENTAGE.value
