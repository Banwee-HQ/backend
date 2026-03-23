"""
Brevo (formerly Sendinblue) email service
"""
import aiohttp
import asyncio
from jinja2 import Environment, FileSystemLoader, select_autoescape
from core.config import settings
from pathlib import Path

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
        "store_launch": "🚀 Store Launch - Welcome to Banwee!",
        "back_in_stock": "🎉 Your Favorite Item is Back in Stock!",
        "cart_abandonment": "🛒 Forgot Something in Your Cart?",
        "price_drop": "💰 Price Drop Alert - Save Now!",
        "browse_abandonment": "👀 Still Thinking About This?",
        "wishlist_reminder": "❤️ A Wishlist Item is Waiting for You",
        "order_confirmation": "✅ Order Confirmation - Thank You!",
        "payment_receipt": "💳 Payment Receipt - Banwee",
        "shipping_update": "📦 Shipping Update for Your Order",
        "order_delivered": "🎉 Your Order Has Been Delivered!",
        "out_for_delivery": "🚚 Your Order is Out for Delivery",
        "partial_shipment": "📦 Partial Shipment Notification",
        "thank_you": "🙏 Thank You for Your Purchase!",
        "review_request": "⭐ Tell Us What You Think",
        "referral_request": "🎁 Refer a Friend & Get Rewards",
        "reorder_reminder": "🔄 Time to Reorder?",
        "return_process": "↩️ Return Instructions",
        "invoice_template": "📄 Your Invoice - Banwee",
        "welcome": "👋 Welcome to Banwee!",
        "onboarding": "🚀 Let's Get You Started",
        "activation": "📧 Verify Your Email Address - Banwee",
        "email_change": "📧 Email Change Confirmation",
        "password_reset": "🔐 Reset Your Password - Banwee",
        "login_alert": "🔔 Login Alert - Banwee",
        "profile_update": "✅ Profile Update Confirmation",
        "subscription_renewal": "🔄 Subscription Renewal Confirmation",
        "newsletter": "📰 Latest News & Offers from Banwee",
        "flash_sale": "⚡ Flash Sale - Don't Miss Out!",
        "birthday_offer": "🎉 Happy Birthday from Banwee!",
        "payment_failed": "⚠️ Payment Failed - Action Required",
        "subscription_payment_failed": "⚠️ Subscription Payment Failed",
        "subscription_update": "🔄 Subscription Update",
        "invoice": "📄 Your Invoice - Banwee",
        "fraud_alert": "🚨 Suspicious Activity Detected",
        "low_stock_alert": "⚠️ Low Stock Alert",
        "policy_update": "📋 We've Updated Our Policies",
        "gdpr_confirmation": "✅ Your GDPR Request",
        "cookie_settings": "🍪 Your Cookie Preferences",
    }

    template_map = {
        "store_launch": "pre_purchase/store_launch.html",
        "back_in_stock": "pre_purchase/back_in_stock.html",
        "cart_abandonment": "pre_purchase/cart_abandonment.html",
        "price_drop": "pre_purchase/price_drop.html",
        "browse_abandonment": "pre_purchase/browse_abandonment.html",
        "wishlist_reminder": "pre_purchase/wishlist_reminder.html",
        "order_confirmation": "purchase/order_confirmation.html",
        "payment_receipt": "purchase/payment_receipt.html",
        "shipping_update": "purchase/shipping_update.html",
        "order_delivered": "purchase/order_delivered.html",
        "out_for_delivery": "purchase/out_for_delivery.html",
        "partial_shipment": "purchase/partial_shipment.html",
        "thank_you": "post_purchase/thank_you.html",
        "review_request": "post_purchase/review_request.html",
        "referral_request": "post_purchase/referral_request.html",
        "reorder_reminder": "post_purchase/reorder_reminder.html",
        "return_process": "post_purchase/return_process.html",
        "invoice_template": "post_purchase/invoice_template.html",
        "welcome": "account/welcome.html",
        "onboarding": "account/onboarding.html",
        "activation": "account/activation.html",
        "email_change": "account/email_change.html",
        "password_reset": "account/password_reset.html",
        "login_alert": "account/login_alert.html",
        "profile_update": "account/profile_update.html",
        "unsubscribe_confirmation": "account/unsubscribe_confirmation.html",
        "subscription_renewal": "account/subscription_renewal.html",
        "subscription_shipment": "account/subscription_shipment.html",
        "newsletter": "marketing/newsletter.html",
        "flash_sale": "marketing/flash_sale.html",
        "birthday_offer": "marketing/birthday_offer.html",
        "payment_failed": "system/payment_failed.html",
        "subscription_payment_failed": "system/subscription_payment_failed.html",
        "subscription_update": "system/subscription_update.html",
        "invoice": "system/invoice.html",
        "fraud_alert": "system/fraud_alert.html",
        "low_stock_alert": "system/low_stock_alert.html",
        "policy_update": "legal/policy_update.html",
        "gdpr_confirmation": "legal/gdpr_confirmation.html",
        "cookie_settings": "legal/cookie_settings.html",
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
