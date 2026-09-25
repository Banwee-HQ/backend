"""Tests for schemas/common/service_types.py - TypedDict shape sanity checks.

TypedDicts aren't validated at runtime, so these confirm the declared keys
match how callers actually construct them (services/commerce/export.py etc.).
"""

from decimal import Decimal

from schemas.common.service_types import CartValidationResult, PricingCalculationResult
from schemas.common.service_types import DiscountCalculationResult, ExportResult


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


class TestDiscountCalculationResult:

    def test_holds_discount_fields(self):
        result: DiscountCalculationResult = {"discount_amount": Decimal("5.00"), "discount_type": "fixed"}
        assert result["discount_type"] == "fixed"


class TestExportResult:

    def test_holds_content_and_metadata(self):
        result: ExportResult = {"content": b"data", "content_type": "text/csv", "filename": "export.csv"}
        assert result["content_type"] == "text/csv"