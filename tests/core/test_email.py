"""Tests for core/utils/messages/email.py - formatting filters and send_email_by_type dispatch."""

from datetime import datetime
import pytest

from core.utils.messages.email import _format_currency, _format_date, _format_datetime, send_email_by_type


class TestFormatCurrency:

    def test_usd_uses_dollar_sign(self):
        assert _format_currency(19.9) == "$19.90"

    def test_other_currency_appends_code(self):
        assert _format_currency(19.9, "EUR") == "19.90 EUR"


class TestFormatDate:

    def test_formats_datetime_objects(self):
        assert _format_date(datetime(2026, 3, 5)) == "March 05, 2026"

    def test_non_datetime_falls_back_to_str(self):
        assert _format_date("already-a-string") == "already-a-string"


class TestFormatDatetime:

    def test_formats_datetime_objects(self):
        assert _format_datetime(datetime(2026, 3, 5, 14, 30)) == "March 05, 2026 at 02:30 PM"

    def test_non_datetime_falls_back_to_str(self):
        assert _format_datetime(42) == "42"


class TestSendEmailByType:

    @pytest.mark.asyncio
    async def test_unknown_mail_type_skips_sending(self, mocker):
        mock_send = mocker.patch("core.utils.messages.email.send_email_brevo")
        result = await send_email_by_type("a@example.com", "not_a_real_type")
        mock_send.assert_not_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_known_mail_type_sends_with_resolved_subject_and_template(self, mocker):
        mock_send = mocker.patch("core.utils.messages.email.send_email_brevo", return_value="ok")
        result = await send_email_by_type("a@example.com", "password_reset", {"reset_link": "https://x"})
        mock_send.assert_awaited_once_with(
            to_email="a@example.com",
            subject="🔐 Reset Your Password - Banwee",
            template_name="account/password_reset.html",
            context={"reset_link": "https://x"},
        )
        assert result == "ok"
