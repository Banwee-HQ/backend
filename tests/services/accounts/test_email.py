"""Tests for services/accounts/email.py - EmailService template rendering and sending."""

import pytest
from datetime import datetime, timezone

from services.accounts.email import EmailService


@pytest.fixture
def service(db_session):
    return EmailService(db_session)


@pytest.fixture(autouse=True)
def mock_send(mocker):
    """Every test in this file only cares that the right template renders and the
    right recipient/subject reach send_email_brevo - never send a real email."""
    return mocker.patch("services.accounts.email.send_email_brevo")


class TestSendOrderConfirmationEmail:

    async def test_sends_with_formatted_items(self, service, mock_send):
        await service.send_order_confirmation_email(
            recipient_email="a@example.com", customer_name="Ada", order_number="ORD-1",
            order_date=datetime.now(timezone.utc), total_amount=49.99,
            items=[{"name": "Widget", "quantity": 2, "price": 19.99}],
        )
        mock_send.assert_awaited_once()
        kwargs = mock_send.call_args.kwargs
        assert kwargs["to_email"] == "a@example.com"
        assert "ORD-1" in kwargs["subject"]


class TestSendVerificationEmail:

    async def test_sends_verification_email(self, service, mock_send):
        await service.send_verification_email("a@example.com", "Ada", "tok123")
        mock_send.assert_awaited_once()
        assert mock_send.call_args.kwargs["to_email"] == "a@example.com"


class TestSendThankYouEmail:

    async def test_sends_with_order_number(self, service, mock_send):
        await service.send_thank_you_email("a@example.com", "Ada", "ORD-1")
        mock_send.assert_awaited_once()

    async def test_sends_without_order_number(self, service, mock_send):
        await service.send_thank_you_email("a@example.com", "Ada")
        mock_send.assert_awaited_once()


class TestSendReviewRequestEmail:

    async def test_sends(self, service, mock_send):
        await service.send_review_request_email("a@example.com", "Ada", "ORD-1")
        mock_send.assert_awaited_once()


class TestSendPasswordResetEmail:

    async def test_sends_with_reset_link(self, service, mock_send):
        await service.send_password_reset_email("a@example.com", "tok", "https://example.com/reset?token=tok")
        mock_send.assert_awaited_once()
        assert "Reset" in mock_send.call_args.kwargs["subject"]


class TestSendShippingUpdateEmail:

    async def test_sends_with_estimated_delivery(self, service, mock_send):
        await service.send_shipping_update_email(
            "a@example.com", "Ada", "ORD-1", "TRACK123", "UPS", datetime.now(timezone.utc)
        )
        mock_send.assert_awaited_once()

    async def test_sends_without_estimated_delivery(self, service, mock_send):
        await service.send_shipping_update_email(
            "a@example.com", "Ada", "ORD-1", "TRACK123", "UPS", None
        )
        mock_send.assert_awaited_once()


class TestSendLowStockAlert:

    async def test_sends_alert(self, service, mock_send):
        """Regression test: system/low_stock_alert.html didn't exist, so this always
        raised TemplateNotFound instead of sending."""
        await service.send_low_stock_alert(
            recipient_email="admin@example.com", product_name="Widget", variant_name="Large",
            location_name="Main Warehouse", current_stock=2, threshold=10,
        )
        mock_send.assert_awaited_once()
        assert "Widget" in mock_send.call_args.kwargs["subject"]


class TestSendOrderDeliveredEmail:

    async def test_sends_with_datetime_delivery_date(self, service, mock_send):
        await service.send_order_delivered_email(
            recipient_email="a@example.com", customer_name="Ada", order_id="1", order_number="ORD-1",
            tracking_number="TRACK123", delivery_date=datetime.now(timezone.utc), delivery_address="1 Test St",
        )
        mock_send.assert_awaited_once()


class TestSendSubscriptionPaymentFailed:

    async def test_sends_retry_message_under_threshold(self, service, mock_send):
        await service.send_subscription_payment_failed(
            user_email="a@example.com", subscription_id="sub-1", subscription_name="Monthly Box",
            error_message="Card declined", retry_count=1,
        )
        mock_send.assert_awaited_once()
        assert "Payment Failed" in mock_send.call_args.kwargs["subject"]

    async def test_sends_paused_message_at_threshold(self, service, mock_send):
        await service.send_subscription_payment_failed(
            user_email="a@example.com", subscription_id="sub-1", subscription_name="Monthly Box",
            error_message="Card declined", retry_count=3,
        )
        mock_send.assert_awaited_once()
        assert "Paused" in mock_send.call_args.kwargs["subject"]


class TestRenderEmailWithTemplate:

    async def test_renders_known_template(self, service):
        content = await service.render_email_with_template("account/activation.html", {
            "customer_name": "Ada", "verification_link": "https://example.com/verify"
        })
        assert "Ada" in content or "verify" in content.lower()

    async def test_raises_for_unknown_template(self, service):
        with pytest.raises(Exception):
            await service.render_email_with_template("does/not_exist.html", {})


class TestSendDirect:

    async def test_sends_via_known_template_map(self, service, mock_send):
        await service._send_direct("verification", "a@example.com", firstname="Ada", verification_token="tok")
        mock_send.assert_awaited_once()

    async def test_falls_back_to_simple_html_for_unknown_mail_type(self, service, mock_send):
        await service._send_direct("some_unmapped_type", "a@example.com", customer_name="Ada")
        mock_send.assert_awaited_once()
        assert "Ada" in mock_send.call_args.kwargs["html_content"]

    async def test_does_not_raise_when_brevo_fails(self, service, mock_send):
        mock_send.side_effect = Exception("Brevo down")
        await service._send_direct("verification", "a@example.com", firstname="Ada", verification_token="tok")


class TestQueueingHelpers:
    """send_shipping_update / send_verification / send_order_delivered queue a
    background task instead of sending directly."""

    def test_send_shipping_update_queues_task(self, service, mocker):
        background_tasks = mocker.Mock()
        service.send_shipping_update(
            background_tasks, "a@example.com", "Ada", "ORD-1", "TRACK123", "UPS", datetime.now(timezone.utc)
        )
        background_tasks.add_task.assert_called_once()
        assert background_tasks.add_task.call_args.args[0] == service._send_direct
        assert background_tasks.add_task.call_args.args[1] == "shipping_update"

    def test_send_verification_queues_task(self, service, mocker):
        background_tasks = mocker.Mock()
        service.send_verification(background_tasks, "a@example.com", "Ada", "tok")
        background_tasks.add_task.assert_called_once()
        assert background_tasks.add_task.call_args.args[1] == "verification"

    def test_send_order_delivered_queues_task(self, service, mocker):
        background_tasks = mocker.Mock()
        service.send_order_delivered(
            background_tasks, "a@example.com", "Ada", "1", "ORD-1", "TRACK123",
            datetime.now(timezone.utc), "1 Test St"
        )
        background_tasks.add_task.assert_called_once()
        assert background_tasks.add_task.call_args.args[1] == "order_delivered"
