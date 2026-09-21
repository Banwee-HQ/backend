"""Tests for schemas/system/contact_message.py."""

import pytest
from pydantic import ValidationError

from schemas.system.contact_message import Create


class TestCreate:

    def test_requires_valid_email(self):
        with pytest.raises(ValidationError):
            Create(name="Ada", email="not-an-email", subject="Question", message="Where is my order?")

    def test_rejects_message_shorter_than_ten_chars(self):
        with pytest.raises(ValidationError):
            Create(name="Ada", email="ada@example.com", subject="Question", message="short")

    def test_accepts_valid_message(self):
        message = Create(name="Ada", email="ada@example.com", subject="Question", message="Where is my order?")
        assert message.subject == "Question"
