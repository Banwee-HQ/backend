"""
Brevo (formerly Sendinblue) email service
"""
import aiohttp
import asyncio
from jinja2 import Environment, FileSystemLoader, select_autoescape
from core.config import settings
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

# Template name mapping for all email types
template_map: Dict[str, str] = {
    "order_confirmation": "purchase/order_confirmation.html",
    "payment_receipt": "purchase/payment_receipt.html",
    "shipping_update": "purchase/shipping_update.html",
    "order_delivered": "purchase/order_delivered.html",
    "partial_shipment": "purchase/partial_shipment.html",
    "digital_delivery": "purchase/digital_delivery.html",
    "thank_you": "post_purchase/thank_you.html",
    "review_request": "post_purchase/review_request.html",
    "referral_request": "post_purchase/referral_request.html",
    "product_tips": "post_purchase/product_tips.html",
    "warranty_reminder": "post_purchase/warranty_reminder.html",
    "activation": "account/activation.html",
    "verification": "account/activation.html",  # Alias for activation
    "email_change": "account/email_change.html",
    "password_reset": "account/password_reset.html",
    "unsubscribe_confirmation": "account/unsubscribe_confirmation.html",
    "subscription_renewal": "account/subscription_renewal.html",
    "subscription_shipment": "account/subscription_shipment.html",
    "birthday_offer": "marketing/birthday_offer.html",
    "cross_sell": "marketing/cross_sell.html",
    "event_invite": "marketing/event_invite.html",
    "holiday_campaign": "marketing/holiday_campaign.html",
    "product_launch": "pre_purchase/product_launch.html",
    "payment_failed": "system/payment_failed.html",
    "subscription_payment_failed": "system/subscription_payment_failed.html",
    "subscription_update": "system/subscription_update.html",
    "invoice": "system/invoice.html",
}

# Jinja2 template environment
template_dir = Path(__file__).parent / "templates"
template_dir.mkdir(parents=True, exist_ok=True)

env = Environment(
    loader=FileSystemLoader(str(template_dir)),
    autoescape=select_autoescape(['html', 'xml']),
    trim_blocks=True,
    lstrip_blocks=True
)


def _format_currency(value: float, currency: str = "USD") -> str:
    return f"${value:.2f}" if currency == "USD" else f"{value:.2f} {currency}"

def _format_date(value) -> str:
    return value.strftime('%B %d, %Y') if hasattr(value, 'strftime') else str(value)

def _format_datetime(value) -> str:
    return value.strftime('%B %d, %Y at %I:%M %p') if hasattr(value, 'strftime') else str(value)

env.filters['currency'] = _format_currency
env.filters['date'] = _format_date
env.filters['datetime'] = _format_datetime


async def render_email(template_name: str, context: dict) -> str:
    """Render a Jinja2 email template."""
    try:
        template = env.get_template(template_name)
        email_context = {
            **context,
            'company_name': context.get('company_name', 'Banwee'),
            'support_email': context.get('support_email', 'support@banwee.com'),
            'current_year': context.get('current_year', '2026'),
            'frontend_url': context.get('frontend_url', settings.FRONTEND_URL),
            'logo_url': context.get('logo_url', f"{settings.FRONTEND_URL}/banwee_logo_green.png"),
        }
        return template.render(**email_context)
    except Exception as e:
        print(f"❌ Template rendering error ({template_name}): {e}")
        raise RuntimeError(f"Template rendering error: {e}")


async def send_email_brevo(
    to_email: str,
    subject: str = None,
    template_name: str = None,
    context: dict = {},
    html_content: str = None
):
    """
    Send an email via Brevo (Sendinblue) transactional API.

    Args:
        to_email: Recipient email address
        subject: Email subject
        template_name: Jinja2 template path (e.g. 'account/welcome.html')
        context: Template context variables
        html_content: Pre-rendered HTML (alternative to template_name)
    """
    if not template_name and not html_content:
        raise ValueError("Either template_name or html_content is required")

    subject = subject or "Notification from Banwee"

    # Render HTML
    if html_content:
        html_body = html_content
    else:
        html_body = await render_email(template_name, context)

    # Parse sender
    from_raw = settings.BREVO_FROM_EMAIL  # e.g. "Banwee <noreply@banwee.com>"
    if '<' in from_raw and '>' in from_raw:
        from_name = from_raw.split('<')[0].strip()
        from_address = from_raw.split('<')[1].split('>')[0].strip()
    else:
        from_name = "Banwee"
        from_address = from_raw.strip()

    payload = {
        "sender": {"name": from_name, "email": from_address},
        "to": [{"email": to_email.strip()}],
        "subject": subject.strip(),
        "htmlContent": html_body,
        "textContent": context.get("text_body", "Please view this email in an HTML-capable client."),
    }

    print(f"📤 Sending email via Brevo to {to_email} — {subject}")

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": settings.BREVO_API_KEY,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            if response.status in (200, 201):
                result = await response.json()
                print(f"✅ Email sent via Brevo: messageId={result.get('messageId')}")
                return result
            else:
                error_text = await response.text()
                print(f"❌ Brevo error ({response.status}): {error_text}")
                raise Exception(f"Brevo API error {response.status}: {error_text}")


# ---------------------------------------------------------------------------
# Legacy alias — keeps all existing callers working unchanged
# ---------------------------------------------------------------------------
send_email_mailjet = send_email_brevo


async def send_email_brevo_legacy(to_email: str, mail_type: str, context: dict = {}):
    """Send email by mail_type key (legacy interface)."""
    subject_map = {
        "order_confirmation": "✅ Order Confirmation - Thank You!",
        "payment_receipt": "💳 Payment Receipt - Banwee",
        "shipping_update": "📦 Shipping Update for Your Order",
        "order_delivered": "🎉 Your Order Has Been Delivered!",
        "partial_shipment": "📦 Partial Shipment Notification",
        "activation": "📧 Verify Your Email Address - Banwee",
        "email_change": "📧 Email Change Confirmation",
        "password_reset": "🔐 Reset Your Password - Banwee",
        "unsubscribe_confirmation": "📧 Unsubscribe Confirmation",
        "subscription_renewal": "🔄 Subscription Renewal Confirmation",
        "subscription_shipment": "📦 Your Subscription Has Shipped!",
        "birthday_offer": "🎉 Happy Birthday from Banwee!",
        "cross_sell": "🛒 You Might Also Like",
        "event_invite": "🎉 You're Invited!",
        "holiday_campaign": "🎄 Special Holiday Offers from Banwee!",
        "product_launch": "🚀 New Product Launch!",
        "payment_failed": "⚠️ Payment Failed - Action Required",
        "subscription_payment_failed": "⚠️ Subscription Payment Failed",
        "subscription_update": "🔄 Subscription Update",
        "invoice": "📄 Your Invoice - Banwee",
    }

    subject = subject_map.get(mail_type, "Notification from Banwee")
    template_name = template_map.get(mail_type)

    if not template_name:
        print(f"⚠️ No template found for mail_type: {mail_type}")
        return

    return await send_email_brevo(
        to_email=to_email,
        subject=subject,
        template_name=template_name,
        context=context
    )


# Legacy alias
send_email_mailjet_legacy = send_email_brevo_legacy


def send_email_brevo_sync(to_email: str, mail_type: str, context: dict = {}):
    """Synchronous wrapper for send_email_brevo_legacy."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(send_email_brevo_legacy(to_email, mail_type, context))
    finally:
        loop.close()


# Legacy aliases
send_email_mailjet_sync = send_email_brevo_sync
send_email = send_email_brevo_sync
