"""Tests for models/commerce/tax_rates.py - TaxRate."""

from decimal import Decimal

from core.utils.uuid_utils import uuid7
from models.commerce.tax_rates import TaxRate


class TestTaxRateRepr:

    def test_includes_province_when_set(self):
        rate = TaxRate(id=uuid7(), country_code="US", country_name="United States", province_code="CA", tax_rate=Decimal("0.0725"))
        assert repr(rate) == "<TaxRate US-CA: 7.2500%>"

    def test_country_only_when_no_province(self):
        rate = TaxRate(id=uuid7(), country_code="NG", country_name="Nigeria", tax_rate=Decimal("0.075"))
        assert repr(rate) == "<TaxRate NG: 7.500%>"
