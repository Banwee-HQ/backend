"""Tests for models/system/contact_message.py - ContactMessage."""

from core.utils.uuid_utils import uuid7
from models.system.contact_message import ContactMessage


class TestContactMessageRepr:

    def test_includes_id_and_subject(self):
        message = ContactMessage(id=uuid7(), name="Ada", email="ada@example.com", subject="Order question", message="Where is my order?")
        assert str(message.id) in repr(message)
        assert "Order question" in repr(message)
