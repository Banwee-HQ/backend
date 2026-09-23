"""Tests for core/utils/messages/email.py - formatting filters, Jinja rendering, the
Brevo HTTP call, and send_email_by_type dispatch.

render_email/send_email_by_type are exercised with the service's own real Jinja
environment and real on-disk templates (no mocking of the code under test);
only the genuinely external side effect - the actual HTTP call to Brevo's API -
is mocked, via aiohttp.ClientSession, per this project's testing convention.
"""

from datetime import datetime
import pytest

from core.utils.messages import email as email_module
from core.utils.messages.email import (
    _format_currency,
    _format_date,
    _format_datetime,
    render_email,
    send_email_brevo,
    send_email_by_type,
)


@pytest.fixture
def temp_template():
    """Write a real template file into the module's actual template directory
    (FileSystemLoader is bound to a fixed path at import time, so a tmp_path
    directory can't be swapped in) and clean it up afterward."""
    subdir = email_module.template_dir / "_pytest_tmp"
    subdir.mkdir(parents=True, exist_ok=True)
    path = subdir / "greeting.html"
    path.write_text("Hi {{ name }}! - {{ company_name }} / {{ frontend_url }} / {{ logo_url }}")
    try:
        yield "_pytest_tmp/greeting.html"
    finally:
        path.unlink(missing_ok=True)
        try:
            subdir.rmdir()
        except OSError:
            pass


class _FakeResponse:
    def __init__(self, status, json_body=None, text_body=""):
        self.status = status
        self._json_body = json_body if json_body is not None else {}
        self._text_body = text_body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def json(self):
        return self._json_body

    async def text(self):
        return self._text_body


class _FakeSession:
    """Fake aiohttp.ClientSession - records the POST call for assertions and
    returns a canned response, so only the genuinely external HTTP call to
    Brevo is faked; everything else in send_email_brevo runs for real."""

    def __init__(self, response):
        self.response = response
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def post(self, url, headers=None, json=None, timeout=None):
        self.post_calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return self.response


def _patch_brevo(mocker, status=200, json_body=None, text_body=""):
    fake_session = _FakeSession(_FakeResponse(status, json_body, text_body))
    mocker.patch("core.utils.messages.email.aiohttp.ClientSession", return_value=fake_session)
    return fake_session


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


class TestRenderEmail:

    @pytest.mark.asyncio
    async def test_renders_real_template_with_default_context(self, temp_template):
        result = await render_email(temp_template, {"name": "Ada"})
        assert "Hi Ada!" in result
        assert "Banwee" in result  # default company_name

    @pytest.mark.asyncio
    async def test_provided_context_overrides_defaults(self, temp_template):
        result = await render_email(temp_template, {"name": "Ada", "company_name": "Acme"})
        assert "Acme" in result
        assert "Banwee" not in result

    @pytest.mark.asyncio
    async def test_unknown_template_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="Template rendering error"):
            await render_email("does-not-exist-at-all.html", {})


class TestSendEmailBrevo:

    @pytest.mark.asyncio
    async def test_requires_template_name_or_html_content(self):
        with pytest.raises(ValueError, match="template_name or html_content"):
            await send_email_brevo(to_email="a@example.com")

    @pytest.mark.asyncio
    async def test_html_content_path_skips_template_rendering(self, mocker):
        fake_session = _patch_brevo(mocker, status=201, json_body={"messageId": "msg-1"})
        result = await send_email_brevo(to_email="a@example.com", html_content="<p>Hi</p>")

        assert result == {"messageId": "msg-1"}
        assert len(fake_session.post_calls) == 1
        assert fake_session.post_calls[0]["json"]["htmlContent"] == "<p>Hi</p>"
        # Default subject applied when none given.
        assert fake_session.post_calls[0]["json"]["subject"] == "Notification from Banwee"

    @pytest.mark.asyncio
    async def test_template_name_path_renders_real_template(self, mocker, temp_template):
        fake_session = _patch_brevo(mocker, status=200, json_body={"messageId": "msg-2"})
        result = await send_email_brevo(
            to_email="a@example.com", subject="Hello", template_name=temp_template, context={"name": "Ada"},
        )

        assert result == {"messageId": "msg-2"}
        assert "Hi Ada!" in fake_session.post_calls[0]["json"]["htmlContent"]
        assert fake_session.post_calls[0]["json"]["subject"] == "Hello"

    @pytest.mark.asyncio
    async def test_sender_parsed_from_name_and_email_format(self, mocker, temp_template):
        mocker.patch.object(email_module.settings, "BREVO_FROM_EMAIL", "Banwee <noreply@banwee.com>")
        fake_session = _patch_brevo(mocker, status=200, json_body={"messageId": "m"})
        await send_email_brevo(to_email="a@example.com", template_name=temp_template, context={})

        sender = fake_session.post_calls[0]["json"]["sender"]
        assert sender == {"name": "Banwee", "email": "noreply@banwee.com"}

    @pytest.mark.asyncio
    async def test_sender_falls_back_to_bare_address_without_angle_brackets(self, mocker, temp_template):
        mocker.patch.object(email_module.settings, "BREVO_FROM_EMAIL", "plain@banwee.com")
        fake_session = _patch_brevo(mocker, status=200, json_body={"messageId": "m"})
        await send_email_brevo(to_email="a@example.com", template_name=temp_template, context={})

        sender = fake_session.post_calls[0]["json"]["sender"]
        assert sender == {"name": "Banwee", "email": "plain@banwee.com"}

    @pytest.mark.asyncio
    async def test_non_2xx_status_raises_with_error_body(self, mocker, temp_template):
        _patch_brevo(mocker, status=400, text_body="invalid recipient")
        with pytest.raises(Exception, match="invalid recipient"):
            await send_email_brevo(to_email="a@example.com", template_name=temp_template, context={})

    @pytest.mark.asyncio
    async def test_text_body_defaults_when_not_provided_in_context(self, mocker, temp_template):
        fake_session = _patch_brevo(mocker, status=200, json_body={"messageId": "m"})
        await send_email_brevo(to_email="a@example.com", template_name=temp_template, context={})
        assert "HTML-capable client" in fake_session.post_calls[0]["json"]["textContent"]


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
