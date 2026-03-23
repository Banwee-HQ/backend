"""
Mailjet email service for sending emails
"""
import aiohttp
import asyncio
from jinja2 import Environment, FileSystemLoader, select_autoescape
from core.config import settings
import os
from pathlib import Path

# Initialize Jinja environment directly to avoid circular imports
# Use absolute path from the backend directory
template_dir = Path(__file__).parent / "templates"
template_dir.mkdir(parents=True, exist_ok=True)

env = Environment(
    loader=FileSystemLoader(str(template_dir)),
    autoescape=select_autoescape(['html', 'xml']),
    trim_blocks=True,
    lstrip_blocks=True
)

# Add custom filters
def _format_currency(value: float, currency: str = "USD") -> str:
    """Format currency values"""
    if currency == "USD":
        return f"${value:.2f}"
    return f"{value:.2f} {currency}"

def _format_date(value) -> str:
    """Format date values"""
    if hasattr(value, 'strftime'):
        return value.strftime('%B %d, %Y')
    return str(value)

def _format_datetime(value) -> str:
    """Format datetime values"""
    if hasattr(value, 'strftime'):
        return value.strftime('%B %d, %Y at %I:%M %p')
    return str(value)

env.filters['currency'] = _format_currency
env.filters['date'] = _format_date
env.filters['datetime'] = _format_datetime


async def render_email(template_name: str, context: dict) -> str:
    """Render Jinja2 template with context"""
    try:
        template = env.get_template(template_name)
        
        # Add common email context variables
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
        print(f"Template rendering error: {e}")
        raise RuntimeError(f"Template rendering error: {e}")


async def send_email_mailjet(
    to_email: str,
    subject: str = None,
    template_name: str = None,
    context: dict = {},
    html_content: str = None
):
    """
    Send email using Mailjet API (async)
    
    Args:
        to_email: Recipient email address
        subject: Email subject line
        template_name: Template file name (e.g., 'account/welcome.html')
        context: Template context variables
        html_content: Pre-rendered HTML content (alternative to template_name)
    """
    
    if not template_name and not html_content:
        raise ValueError("Either template_name or html_content is required")
    
    if not subject:
        subject = "Notification from Banwee"

    try:
        # Use pre-rendered HTML if provided, otherwise render template
        if html_content:
            html_body = html_content
            print(f"🔧 Debug: Using provided html_content ({len(html_body)} chars)")
        else:
            html_body = await render_email(template_name, context)
            print(f"🔧 Debug: Rendered template {template_name} ({len(html_body)} chars)")
        
        text_body = context.get("text_body", "This is a plain-text fallback.")
        print(f"🔧 Debug: text_body = '{text_body}'")
        
        print(f'📤 Sending email via Mailjet to {to_email}...')

        # Mailjet API endpoint (v3.1)
        mailjet_url = "https://api.mailjet.com/v3.1/send"
        
        # Parse from email
        from_email = settings.MAILJET_FROM_EMAIL
        print(f"🔧 Debug: MAILJET_FROM_EMAIL = '{from_email}'")
        
        if '<' in from_email and '>' in from_email:
            # Format: "Name <email@domain.com>"
            from_name = from_email.split('<')[0].strip()
            from_address = from_email.split('<')[1].split('>')[0].strip()
        else:
            # Format: "email@domain.com"
            from_name = "Banwee"
            from_address = from_email
        
        # Ensure from_address is not empty and is a valid email
        if not from_address or '@' not in from_address:
            print(f"🔧 Debug: Invalid from_address '{from_address}', using fallback")
            from_address = "oscarchiagoziem@gmail.com"
            from_name = "BanweeTest"
        
        print(f"🔧 Debug: from_name = '{from_name}', from_address = '{from_address}'")
        
        # Prepare Mailjet payload (v3.0 format - working version)
        payload = {
            "FromEmail": str(from_address).strip(),
            "FromName": str(from_name).strip(),
            "Recipients": [
                {
                    "Email": str(to_email).strip(),
                    "Name": str(context.get("to_name", "") or "").strip()
                }
            ],
            "Subject": str(subject).strip(),
            "Text-part": str(text_body).strip(),
            "Html-part": str(html_body).strip()
        }
        
        print(f"🔧 Debug: Using Mailjet v3.0 format - FromEmail: '{payload['FromEmail']}'")
        
        # Send async request to Mailjet (use v3.0 since v3.1 has issues)
        async with aiohttp.ClientSession() as session:
            try:
                # Use v3.0 API which works correctly
                async with session.post(
                    "https://api.mailjet.com/v3/send",
                    auth=aiohttp.BasicAuth(settings.MAILJET_API_KEY, settings.MAILJET_API_SECRET),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        print(f"✅ Email sent successfully via Mailjet v3.0: {result}")
                        return result
                    else:
                        error_text = await response.text()
                        print(f"❌ Mailjet error ({response.status}): {error_text}")
                        raise Exception(f"Mailjet API error: {error_text}")
            except Exception as e:
                print(f"❌ Exception during Mailjet request: {e}")
                raise

    except asyncio.TimeoutError:
        print("❌ Request timed out.")
        raise

    except Exception as err:
        print(f"❌ Unexpected error: {err}")
        raise


# Legacy function for backward compatibility with old mail_type system
async def send_email_mailjet_legacy(
    to_email: str,
    mail_type: str,
    context: dict = {}
):
    """
    Legacy function for backward compatibility
    """
    
    subject_map = {
        # Pre-Purchase / Lead Nurturing
        "store_launch": "🚀 Store Launch - Welcome to Banwee!",
        "waitlist_notification": "✅ Back in Stock Alert!",
        "product_launch": "🚀 New Product Launch - Check It Out!",
        "back_in_stock": "🎉 Your Favorite Item is Back in Stock!",
        "cart_abandonment": "🛒 Forgot Something in Your Cart?",
        "price_drop": "💰 Price Drop Alert - Save Now!",
        "browse_abandonment": "👀 Still Thinking About This?",
        "wishlist_reminder": "❤️ A Wishlist Item is Waiting for You",

        # Purchase Related
        "order_confirmation": "✅ Order Confirmation - Thank You!",
        "payment_receipt": "💳 Payment Receipt - Banwee",
        "shipping_update": "📦 Shipping Update for Your Order",
        "order_delivered": "🎉 Your Order Has Been Delivered!",
        "digital_delivery": "📥 Your Digital Product is Ready",
        "out_for_delivery": "🚚 Your Order is Out for Delivery",
        "partial_shipment": "📦 Partial Shipment Notification",

        # Post-Purchase
        "thank_you": "🙏 Thank You for Your Purchase!",
        "review_request": "⭐ Tell Us What You Think",
        "referral_request": "🎁 Refer a Friend & Get Rewards",
        "product_tips": "💡 How to Use Your Product",
        "warranty_reminder": "🛡️ Register Your Warranty",
        "reorder_reminder": "🔄 Time to Reorder?",
        "return_process": "↩️ Return Instructions",
        "invoice_template": "📄 Your Invoice - Banwee",

        # Account & Engagement
        "welcome": "👋 Welcome to Banwee!",
        "onboarding": "🚀 Let's Get You Started",
        "activation": "📧 Verify Your Email Address - Banwee",
        "email_change": "📧 Email Change Confirmation",
        "password_reset": "🔐 Reset Your Password - Banwee",
        "login_alert": "🔔 Login Alert - Banwee",
        "profile_update": "✅ Profile Update Confirmation",
        "subscription_renewal": "🔄 Subscription Renewal Confirmation",
        "subscription_shipment": "📦 Subscription Shipment Update",

        # Marketing
        "newsletter": "📰 Latest News & Offers from Banwee",
        "flash_sale": "⚡ Flash Sale - Don't Miss Out!",
        "holiday_campaign": "🎄 Seasonal Special Just for You",
        "loyalty_update": "🎁 Your Loyalty Perks",
        "birthday_offer": "🎉 Happy Birthday from Banwee!",
        "cross_sell": "💡 You Might Also Like These",
        "event_invite": "🎉 You're Invited!",

        # Transactional / System
        "payment_failed": "⚠️ Payment Failed - Action Required",
        "subscription_payment_failed": "⚠️ Subscription Payment Failed",
        "subscription_update": "🔄 Subscription Update",
        "invoice": "📄 Your Invoice - Banwee",
        "fraud_alert": "🚨 Suspicious Activity Detected",
        "low_stock_alert": "⚠️ Low Stock Alert",
        "maintenance_notice": "🔧 Scheduled Maintenance",
        
        # New subscription-related emails
        "subscription_cost_change": "💰 Your Subscription Cost Has Changed",
        "payment_confirmation": "✅ Payment Confirmation - Thank You!",
        "payment_failure": "⚠️ Payment Issue - Action Required",
        "payment_method_expiring": "⚠️ Your Payment Method is Expiring Soon",

        # Legal / Compliance
        "policy_update": "📋 We've Updated Our Policies",
        "gdpr_confirmation": "✅ Your GDPR Request",
        "cookie_settings": "🍪 Your Cookie Preferences",
    }

    template_map = {
        # Pre-Purchase
        "store_launch": "pre_purchase/store_launch.html",
        "waitlist_notification": "pre_purchase/waitlist_notification.html",
        "product_launch": "pre_purchase/product_launch.html",
        "back_in_stock": "pre_purchase/back_in_stock.html",
        "cart_abandonment": "pre_purchase/cart_abandonment.html",
        "price_drop": "pre_purchase/price_drop.html",
        "browse_abandonment": "pre_purchase/browse_abandonment.html",
        "wishlist_reminder": "pre_purchase/wishlist_reminder.html",

        # Purchase Related
        "order_confirmation": "purchase/order_confirmation.html",
        "payment_receipt": "purchase/payment_receipt.html",
        "shipping_update": "purchase/shipping_update.html",
        "order_delivered": "purchase/order_delivered.html",
        "digital_delivery": "purchase/digital_delivery.html",
        "out_for_delivery": "purchase/out_for_delivery.html",
        "partial_shipment": "purchase/partial_shipment.html",

        # Post-Purchase
        "thank_you": "post_purchase/thank_you.html",
        "review_request": "post_purchase/review_request.html",
        "referral_request": "post_purchase/referral_request.html",
        "product_tips": "post_purchase/product_tips.html",
        "warranty_reminder": "post_purchase/warranty_reminder.html",
        "reorder_reminder": "post_purchase/reorder_reminder.html",
        "return_process": "post_purchase/return_process.html",
        "invoice_template": "post_purchase/invoice_template.html",

        # Account & Engagement
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

        # Marketing
        "newsletter": "marketing/newsletter.html",
        "flash_sale": "marketing/flash_sale.html",
        "holiday_campaign": "marketing/holiday_campaign.html",
        "loyalty_update": "marketing/loyalty_update.html",
        "birthday_offer": "marketing/birthday_offer.html",
        "cross_sell": "marketing/cross_sell.html",
        "event_invite": "marketing/event_invite.html",

        # Transactional / System
        "payment_failed": "system/payment_failed.html",
        "subscription_payment_failed": "system/subscription_payment_failed.html",
        "subscription_update": "system/subscription_update.html",
        "invoice": "system/invoice.html",
        "fraud_alert": "system/fraud_alert.html",
        "low_stock_alert": "system/low_stock_alert.html",
        "maintenance_notice": "system/maintenance_notice.html",
        
        # New subscription-related emails
        "subscription_cost_change": "system/subscription_update.html",
        "payment_confirmation": "purchase/payment_receipt.html",
        "payment_failure": "system/payment_failed.html",
        "payment_method_expiring": "system/payment_failed.html",

        # Legal / Compliance
        "policy_update": "legal/policy_update.html",
        "gdpr_confirmation": "legal/gdpr_confirmation.html",
        "cookie_settings": "legal/cookie_settings.html",
    }

    subject = subject_map.get(mail_type, "Notification")
    template_name = template_map.get(mail_type)

    if not template_name:
        print(f"No template found for mail_type: {mail_type}")
        return

    return await send_email_mailjet(
        to_email=to_email,
        subject=subject,
        template_name=template_name,
        context=context
    )


# Synchronous wrapper for backward compatibility
def send_email_mailjet_sync(to_email: str, mail_type: str, context: dict = {}):
    """
    Synchronous wrapper for send_email_mailjet_legacy
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            send_email_mailjet_legacy(to_email, mail_type, context)
        )
    finally:
        loop.close()


# Alias for backward compatibility
send_email = send_email_mailjet_sync
