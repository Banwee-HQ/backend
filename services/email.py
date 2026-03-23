from uuid import UUID
from typing import List, Dict, Any, Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import BackgroundTasks

from models.user import User, Address
from models.orders import Order
from models.product import ProductVariant
from services.templates import JinjaTemplateService
from core.config import settings
from core.errors import APIException
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)


# ============================================================================
# EMAIL SERVICE - All email logic and sending
# ============================================================================

class EmailService:
    """
    Centralized email service that handles all email operations.
    Used by ARQ worker to send emails with proper template rendering.
    """
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.template_service = JinjaTemplateService(template_dir="core/utils/messages/templates")

    async def _get_user_by_id(self, user_id: UUID) -> User:
        result = await self.db_session.execute(select(User).filter(User.id == user_id))
        user = result.scalars().first()
        if not user:
            raise APIException(status_code=404, message="User not found for email operation.")
        return user

    async def _get_order_by_id(self, order_id: UUID) -> Order:
        result = await self.db_session.execute(select(Order).filter(Order.id == order_id))
        order = result.scalars().first()
        if not user:
            raise APIException(status_code=404, message="Order not found for email operation.")
        return order

    async def _get_address_by_id(self, address_id: UUID) -> Optional[Address]:
        result = await self.db_session.execute(select(Address).filter(Address.id == address_id))
        return result.scalars().first()

    async def _get_product_variant_by_id(self, variant_id: UUID) -> Optional[ProductVariant]:
        result = await self.db_session.execute(select(ProductVariant).filter(ProductVariant.id == variant_id))
        return result.scalars().first()

    async def send_order_confirmation_email(
        self,
        recipient_email: str,
        customer_name: str,
        order_number: str,
        order_date: datetime,
        total_amount: float,
        items: List[Dict[str, Any]] = None,
        shipping_address: Dict[str, Any] = None
    ):
        """Send order confirmation email (called from ARQ worker)"""
        # Format items with proper price display
        formatted_items = []
        for item in (items or []):
            formatted_items.append({
                "name": item.get("name", "Item"),
                "quantity": item.get("quantity", 1),
                "price": f"${float(item.get('price', 0)):.2f}"
            })
        
        context = {
            "customer_name": customer_name,
            "order_number": order_number,
            "order_date": order_date.strftime("%B %d, %Y") if isinstance(order_date, datetime) else order_date,
            "order_total": f"${total_amount:.2f}",
            "order_items": formatted_items,
            "shipping_address": shipping_address or {},
            "order_tracking_url": f"{settings.FRONTEND_URL}/account/orders",
            "payment_method": "Card",
            "estimated_delivery": "3-5 business days",
            "company_name": "Banwee",
            "support_email": "support@banwee.com",
            "current_year": datetime.now().year,
            "unsubscribe_url": f"{settings.FRONTEND_URL}/unsubscribe",
            "privacy_policy_url": f"{settings.FRONTEND_URL}/privacy"
        }
        
        html_content = await self.render_email_with_template("purchase/order_confirmation.html", context)
        
        from core.utils.messages.email import send_email_mailjet
        await send_email_mailjet(
            to_email=recipient_email,
            subject=f"Order Confirmation - {order_number}",
            html_content=html_content
        )
        print(f"📧 Order confirmation email sent to {recipient_email}")

    async def send_welcome_email(
        self,
        recipient_email: str,
        user_name: str
    ):
        """Send welcome email (called from ARQ worker)"""
        context = {
            "user_name": user_name,
            "email": recipient_email,
            "store_url": settings.FRONTEND_URL,
            "company_name": "Banwee",
            "support_email": "support@banwee.com",
            "current_year": datetime.now().year
        }
        
        html_content = await self.render_email_with_template("account/welcome.html", context)
        
        from core.utils.messages.email import send_email_mailjet
        await send_email_mailjet(
            to_email=recipient_email,
            subject="Welcome to Banwee!",
            html_content=html_content
        )
        print(f"📧 Welcome email sent to {recipient_email}")

    async def send_password_reset_email(
        self,
        recipient_email: str,
        reset_token: str,
        reset_link: str
    ):
        """Send password reset email (called from ARQ worker)"""
        context = {
            "user_name": "User",
            "reset_link": reset_link or f"{settings.FRONTEND_URL}/reset-password?token={reset_token}",
            "expiry_time": "1 hour",
            "company_name": "Banwee",
            "support_email": "support@banwee.com",
            "current_year": datetime.now().year
        }
        
        html_content = await self.render_email_with_template("account/password_reset.html", context)
        
        from core.utils.messages.email import send_email_mailjet
        await send_email_mailjet(
            to_email=recipient_email,
            subject="Reset Your Password",
            html_content=html_content
        )
        print(f"📧 Password reset email sent to {recipient_email}")

    async def send_shipping_update_email(
        self, 
        recipient_email: str,
        customer_name: str,
        order_number: str,
        tracking_number: str,
        carrier: str,
        estimated_delivery: Optional[datetime],
        tracking_url: Optional[str] = None
    ):
        """Send shipping update email (called from ARQ worker)"""
        context = {
            "customer_name": customer_name,
            "order_number": order_number,
            "tracking_number": tracking_number,
            "carrier_name": carrier,
            "estimated_delivery_date": estimated_delivery.strftime("%B %d, %Y") if estimated_delivery else "3-5 business days",
            "tracking_url": tracking_url or f"https://www.google.com/search?q={carrier}+{tracking_number}",
            "shipping_address": {
                "line1": "",
                "city": "",
                "state_zip": ""
            },
            "order_items": [],
            "company_name": "Banwee",
            "support_email": "support@banwee.com",
            "current_year": datetime.now().year
        }
        
        html_content = await self.render_email_with_template("purchase/shipping_update.html", context)
        
        from core.utils.messages.email import send_email_mailjet
        await send_email_mailjet(
            to_email=recipient_email,
            subject=f"Your Order {order_number} Has Shipped!",
            html_content=html_content
        )
        print(f"📧 Shipping update email sent to {recipient_email}")

    async def send_low_stock_alert(
        self,
        recipient_email: str,
        product_name: str,
        variant_name: str,
        location_name: str,
        current_stock: int,
        threshold: int
    ):
        """Send low stock alert email"""
        context = {
            "recipient_email": recipient_email,
            "product_name": product_name,
            "variant_name": variant_name,
            "location_name": location_name,
            "current_stock": current_stock,
            "threshold": threshold,
            "admin_inventory_link": f"{settings.FRONTEND_URL}/admin/inventory",
            "company_name": "Banwee",
            "support_email": "support@banwee.com",
            "current_year": datetime.now().year
        }
        
        html_content = await self.render_email_with_template("system/low_stock_alert.html", context)
        
        from core.utils.messages.email import send_email_mailjet
        await send_email_mailjet(
            to_email=recipient_email,
            subject=f"Low Stock Alert: {product_name}",
            html_content=html_content
        )
        print(f"📧 Low stock alert sent to {recipient_email}")

    async def send_order_delivered_email(
        self,
        recipient_email: str,
        customer_name: str,
        order_id: str,
        order_number: str,
        tracking_number: str,
        delivery_date: datetime,
        delivery_address: str,
        delivery_notes: Optional[str] = None
    ):
        """Send order delivered email (called from ARQ worker)"""
        context = {
            "customer_name": customer_name,
            "order_id": order_number or order_id,
            "order_number": order_number or order_id,
            "tracking_number": tracking_number or "N/A",
            "delivery_date": delivery_date.strftime("%B %d, %Y") if isinstance(delivery_date, datetime) else delivery_date,
            "delivery_time": delivery_date.strftime("%I:%M %p") if isinstance(delivery_date, datetime) else "",
            "delivery_address": delivery_address,
            "delivery_notes": delivery_notes,
            "track_order_url": f"{settings.FRONTEND_URL}/account/orders/{order_id}",
            "contact_us_url": f"{settings.FRONTEND_URL}/contact",
            "company_name": "Banwee",
            "support_email": "support@banwee.com",
            "current_year": datetime.now().year,
            "unsubscribe_url": f"{settings.FRONTEND_URL}/unsubscribe",
            "privacy_policy_url": f"{settings.FRONTEND_URL}/privacy",
            "logo_url": f"{settings.FRONTEND_URL}/logo.png",
            "social_links": {
                "facebook": "https://facebook.com/banwee",
                "twitter": "https://twitter.com/banwee",
                "instagram": "https://instagram.com/banwee"
            }
        }
        
        html_content = await self.render_email_with_template("purchase/order_delivered.html", context)
        
        from core.utils.messages.email import send_email_mailjet
        await send_email_mailjet(
            to_email=recipient_email,
            subject=f"Your Order {order_number} Has Been Delivered!",
            html_content=html_content
        )
        print(f"📧 Order delivered email sent to {recipient_email}")

    async def send_subscription_payment_failed(
        self,
        user_email: str,
        subscription_id: str,
        subscription_name: str,
        error_message: str,
        retry_count: int
    ):
        """Send subscription payment failed notification email"""
        context = {
            "subscription_name": subscription_name,
            "subscription_id": subscription_id,
            "error_message": error_message,
            "retry_count": retry_count,
            "update_payment_url": f"{settings.FRONTEND_URL}/account/subscriptions/{subscription_id}/payment",
            "subscription_url": f"{settings.FRONTEND_URL}/account/subscriptions/{subscription_id}",
            "company_name": "Banwee",
            "support_email": "support@banwee.com",
            "current_year": datetime.now().year,
            "unsubscribe_url": f"{settings.FRONTEND_URL}/unsubscribe",
            "privacy_policy_url": f"{settings.FRONTEND_URL}/privacy"
        }
        
        # Determine subject based on retry count
        if retry_count >= 3:
            subject = f"Subscription Paused - Payment Failed"
            context["is_paused"] = True
            context["message"] = (
                f"We've attempted to process payment for your subscription '{subscription_name}' "
                f"three times, but all attempts have failed. Your subscription has been paused."
            )
        else:
            subject = f"Payment Failed - Subscription '{subscription_name}'"
            context["is_paused"] = False
            context["message"] = (
                f"We were unable to process payment for your subscription '{subscription_name}'. "
                f"We'll automatically retry the payment soon."
            )
        
        html_content = await self.render_email_with_template("system/subscription_payment_failed.html", context)
        
        from core.utils.messages.email import send_email_mailjet
        await send_email_mailjet(
            to_email=user_email,
            subject=subject,
            html_content=html_content
        )
        print(f"📧 Subscription payment failed email sent to {user_email}")

    async def render_email_with_template(
        self,
        template_name: str,
        context: Dict[str, Any]
    ) -> str:
        """Render an email using Jinja template"""
        try:
            rendered = await self.template_service.render_email_template(template_name, context)
            return rendered.content
        except Exception as e:
            print(f"❌ Failed to render email template {template_name}: {e}")
            raise


# ============================================================================
# EMAIL QUEUE - Class-based wrapper to queue emails via ARQ
# ============================================================================

class EmailQueue:
    """
    Handles queuing of emails via ARQ.
    All application code should use this class to send emails.
    """
    
    @staticmethod
    async def _queue_via_arq(email_type: str, recipient: str, **kwargs):
        """Helper to queue email via ARQ"""
        from core.arq_worker import get_arq_pool
        try:
            pool = await get_arq_pool()
            if pool:
                await pool.enqueue_job('send_email_task', email_type, recipient, **kwargs)
            else:
                print(f"⚠️ ARQ pool not available, email not queued: {email_type} to {recipient}")
        except Exception as e:
            print(f"❌ Failed to queue email via ARQ: {e}")

    @classmethod
    def send_order_confirmation(
        cls,
        background_tasks: BackgroundTasks,
        to_email: str,
        customer_name: str,
        order_number: str,
        order_date: datetime,
        total_amount: float,
        items: List[Dict[str, Any]] = None,
        shipping_address: Dict[str, Any] = None
    ):
        """Queue order confirmation email"""
        background_tasks.add_task(
            cls._queue_via_arq,
            "order_confirmation",
            to_email,
            customer_name=customer_name,
            order_number=order_number,
            order_date=order_date,
            total_amount=total_amount,
            items=items or [],
            shipping_address=shipping_address or {}
        )

    @classmethod
    def send_shipping_update(
        cls,
        background_tasks: BackgroundTasks,
        to_email: str,
        customer_name: str,
        order_number: str,
        tracking_number: str,
        carrier: str,
        estimated_delivery: datetime,
        tracking_url: Optional[str] = None
    ):
        """Queue shipping update email"""
        background_tasks.add_task(
            cls._queue_via_arq,
            "shipping_update",
            to_email,
            customer_name=customer_name,
            order_number=order_number,
            tracking_number=tracking_number,
            carrier=carrier,
            estimated_delivery=estimated_delivery,
            tracking_url=tracking_url
        )

    @classmethod
    def send_welcome(
        cls,
        background_tasks: BackgroundTasks,
        to_email: str,
        user_name: str
    ):
        """Queue welcome email"""
        background_tasks.add_task(
            cls._queue_via_arq,
            "welcome",
            to_email,
            user_name=user_name
        )

    @classmethod
    def send_password_reset(
        cls,
        background_tasks: BackgroundTasks,
        to_email: str,
        reset_token: str,
        reset_link: str
    ):
        """Queue password reset email"""
        background_tasks.add_task(
            cls._queue_via_arq,
            "password_reset",
            to_email,
            reset_token=reset_token,
            reset_link=reset_link
        )

    @classmethod
    def send_order_delivered(
        cls,
        background_tasks: BackgroundTasks,
        to_email: str,
        customer_name: str,
        order_id: str,
        order_number: str,
        tracking_number: str,
        delivery_date: datetime,
        delivery_address: str,
        delivery_notes: Optional[str] = None
    ):
        """Queue order delivered email"""
        background_tasks.add_task(
            cls._queue_via_arq,
            "order_delivered",
            to_email,
            customer_name=customer_name,
            order_id=order_id,
            order_number=order_number,
            tracking_number=tracking_number,
            delivery_date=delivery_date,
            delivery_address=delivery_address,
            delivery_notes=delivery_notes
        )


# ============================================================================
# LEGACY FUNCTION WRAPPERS - For backward compatibility
# ============================================================================

def send_order_confirmation_email(background_tasks: BackgroundTasks, to_email: str, **kwargs):
    """Legacy wrapper - use EmailQueue.send_order_confirmation instead"""
    EmailQueue.send_order_confirmation(background_tasks, to_email, **kwargs)


def send_shipping_update_email(background_tasks: BackgroundTasks, to_email: str, **kwargs):
    """Legacy wrapper - use EmailQueue.send_shipping_update instead"""
    EmailQueue.send_shipping_update(background_tasks, to_email, **kwargs)


def send_welcome_email(background_tasks: BackgroundTasks, to_email: str, **kwargs):
    """Legacy wrapper - use EmailQueue.send_welcome instead"""
    EmailQueue.send_welcome(background_tasks, to_email, **kwargs)


def send_password_reset_email(background_tasks: BackgroundTasks, to_email: str, **kwargs):
    """Legacy wrapper - use EmailQueue.send_password_reset instead"""
    EmailQueue.send_password_reset(background_tasks, to_email, **kwargs)


def send_order_delivered_email(background_tasks: BackgroundTasks, to_email: str, **kwargs):
    """Legacy wrapper - use EmailQueue.send_order_delivered instead"""
    EmailQueue.send_order_delivered(background_tasks, to_email, **kwargs)

