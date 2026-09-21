"""Tests for schemas/accounts/user.py - AddressBase and Base normalization validators."""

import pytest
from pydantic import ValidationError

from schemas.accounts.user import AddressBase, Base, Create, Response


class TestAddressBaseNormalizeFields:

    def test_defaults_missing_state_and_post_code_to_empty_string(self):
        address = AddressBase(street="1 Main St", city="Metropolis", country="US")
        assert address.state == ""
        assert address.post_code == ""

    def test_keeps_provided_state_and_post_code(self):
        address = AddressBase(street="1 Main St", city="Metropolis", country="US", state="NY", post_code="10001")
        assert address.state == "NY"
        assert address.post_code == "10001"


class TestBaseNormalizeNames:

    def test_falls_back_to_first_name_last_name_aliases(self):
        user = Base(email="a@example.com", first_name="Ada", last_name="Lovelace")
        assert user.firstname == "Ada"
        assert user.lastname == "Lovelace"

    def test_prefers_firstname_lastname_over_aliases(self):
        user = Base(email="a@example.com", firstname="Grace", last_name="Lovelace")
        assert user.firstname == "Grace"

    def test_defaults_to_empty_string_when_nothing_provided(self):
        user = Base(email="a@example.com")
        assert user.firstname == ""
        assert user.lastname == ""

    def test_invalid_email_raises(self):
        with pytest.raises(ValidationError):
            Base(email="not-an-email")


class TestCreate:

    def test_requires_password(self):
        with pytest.raises(ValidationError):
            Create(email="a@example.com")

    def test_creates_with_password(self):
        user = Create(email="a@example.com", password="secret123")
        assert user.password == "secret123"
        assert user.firstname == ""


class TestResponse:

    def test_requires_all_core_fields(self):
        with pytest.raises(ValidationError):
            Response(email="a@example.com")
