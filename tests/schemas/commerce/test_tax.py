"""Tests for schemas/commerce/tax.py - tax rate constraints."""

import pytest
from pydantic import ValidationError

from schemas.commerce.tax import RateCreate


class TestRateCreateConstraints:

    def test_rejects_tax_rate_above_one(self):
        with pytest.raises(ValidationError):
            RateCreate(country_code="US", country_name="United States", tax_rate=1.5)

    def test_rejects_country_code_not_two_chars(self):
        with pytest.raises(ValidationError):
            RateCreate(country_code="USA", country_name="United States", tax_rate=0.08)

    def test_accepts_valid_rate(self):
        rate = RateCreate(country_code="US", country_name="United States", tax_rate=0.0725)
        assert rate.is_active is True
