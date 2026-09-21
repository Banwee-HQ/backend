"""Tests for schemas/commerce/carrier.py."""

import pytest
from pydantic import ValidationError

from schemas.commerce.carrier import Create


class TestCreate:

    def test_requires_code_and_name(self):
        with pytest.raises(ValidationError):
            Create(code="ups")

    def test_defaults_is_active_true(self):
        carrier = Create(code="ups", name="UPS")
        assert carrier.is_active is True
