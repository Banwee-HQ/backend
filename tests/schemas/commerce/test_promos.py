"""Tests for schemas/commerce/promos.py - value/code constraints."""

import pytest
from pydantic import ValidationError

from schemas.commerce.promos import Base


class TestBaseConstraints:

    def test_rejects_zero_value(self):
        with pytest.raises(ValidationError):
            Base(code="SAVE10", discount_type="percentage", value=0)

    def test_rejects_empty_code(self):
        with pytest.raises(ValidationError):
            Base(code="", discount_type="percentage", value=10)

    def test_accepts_valid_promo(self):
        promo = Base(code="SAVE10", discount_type="percentage", value=10)
        assert promo.is_active is True
