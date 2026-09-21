"""Tests for models/commerce/validation_rules.py - TaxValidationRule, ShippingValidationRule."""

from decimal import Decimal

from core.utils.uuid_utils import uuid7
from models.commerce.validation_rules import TaxValidationRule, ShippingValidationRule


class TestTaxValidationRuleCalculateTax:

    def test_calculates_percentage_tax(self):
        rule = TaxValidationRule(id=uuid7(), location_code="US-CA", tax_rate=Decimal("0.08"), minimum_tax=Decimal("0.01"), is_active=True)
        assert rule.calculate_tax(100.0) == 8.0

    def test_enforces_minimum_tax(self):
        rule = TaxValidationRule(id=uuid7(), location_code="US-CA", tax_rate=Decimal("0.08"), minimum_tax=Decimal("5.00"), is_active=True)
        assert rule.calculate_tax(1.0) == Decimal("5.00")

    def test_inactive_rule_returns_zero(self):
        rule = TaxValidationRule(id=uuid7(), location_code="US-CA", tax_rate=Decimal("0.08"), minimum_tax=Decimal("0.01"), is_active=False)
        assert rule.calculate_tax(100.0) == 0.0


class TestShippingValidationRuleCalculateShipping:

    def test_calculates_weight_based_rate_within_range(self):
        rule = ShippingValidationRule(
            id=uuid7(), location_code="US", weight_min=Decimal("0.0"), weight_max=Decimal("10.0"),
            base_rate=Decimal("5.00"), minimum_shipping=Decimal("0.01"), is_active=True,
        )
        assert rule.calculate_shipping(2.0) == Decimal("6.00")  # 5.00 + 2*0.5

    def test_out_of_range_weight_returns_zero(self):
        rule = ShippingValidationRule(
            id=uuid7(), location_code="US", weight_min=Decimal("0.0"), weight_max=Decimal("10.0"),
            base_rate=Decimal("5.00"), minimum_shipping=Decimal("0.01"), is_active=True,
        )
        assert rule.calculate_shipping(11.0) == 0.0

    def test_inactive_rule_returns_zero(self):
        rule = ShippingValidationRule(
            id=uuid7(), location_code="US", weight_min=Decimal("0.0"), weight_max=Decimal("10.0"),
            base_rate=Decimal("5.00"), minimum_shipping=Decimal("0.01"), is_active=False,
        )
        assert rule.calculate_shipping(2.0) == 0.0

    def test_enforces_minimum_shipping(self):
        rule = ShippingValidationRule(
            id=uuid7(), location_code="US", weight_min=Decimal("0.0"), weight_max=Decimal("10.0"),
            base_rate=Decimal("0.00"), minimum_shipping=Decimal("3.00"), is_active=True,
        )
        assert rule.calculate_shipping(0.1) == Decimal("3.00")


class TestShippingValidationRuleAppliesToWeight:

    def test_true_within_range_and_active(self):
        rule = ShippingValidationRule(
            id=uuid7(), location_code="US", weight_min=Decimal("1.0"), weight_max=Decimal("5.0"),
            base_rate=Decimal("5.00"), is_active=True,
        )
        assert rule.applies_to_weight(3.0) is True

    def test_false_when_inactive(self):
        rule = ShippingValidationRule(
            id=uuid7(), location_code="US", weight_min=Decimal("1.0"), weight_max=Decimal("5.0"),
            base_rate=Decimal("5.00"), is_active=False,
        )
        assert rule.applies_to_weight(3.0) is False

    def test_false_outside_range(self):
        rule = ShippingValidationRule(
            id=uuid7(), location_code="US", weight_min=Decimal("1.0"), weight_max=Decimal("5.0"),
            base_rate=Decimal("5.00"), is_active=True,
        )
        assert rule.applies_to_weight(6.0) is False
