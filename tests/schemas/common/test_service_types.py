"""Tests for schemas/common/service_types.py - TypedDict shape sanity checks.

TypedDicts aren't validated at runtime, so these confirm the declared keys
match how callers actually construct them (services/commerce/export.py etc.).
"""

from decimal import Decimal

from schemas.common.service_types import CartValidationResult, PricingCalculationResult


class TestCartValidationResult:

    def test_accepts_partial_keys(self):
        result: CartValidationResult = {"valid": True, "can_checkout": True}
        assert result["valid"] is True


class TestPricingCalculationResult:

    def test_holds_decimal_amounts(self):
        result: PricingCalculationResult = {
            "subtotal": Decimal("10.00"), "tax_amount": Decimal("0.80"), "total_amount": Decimal("10.80"),
        }
        assert result["total_amount"] == Decimal("10.80")


