"""
Background task worker — ARQ/Redis removed.
Uses asyncio for scheduled jobs and FastAPI BackgroundTasks for one-off tasks.
"""
import asyncio
from typing import Dict, Any
from datetime import datetime
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)


def _get_db_session():
    """Get database session using the DatabaseManager."""
    try:
        import core.db as core_db
        if hasattr(core_db, 'db_manager') and core_db.db_manager:
            return core_db.db_manager.get_session_with_retry()
    except Exception:
        pass
    return None


# ============================================================================
# EMAIL TASKS
# ============================================================================

async def send_email_task(email_type: str, recipient: str, **kwargs) -> str:
    session = _get_db_session()
    if not session:
        print("❌ DB session not available for email task")
        return "failed"
    
    try:
        from services.accounts.email import EmailService
        async with session as db:
            email_service = EmailService(db)

            if email_type == "verification":
                await email_service.send_verification_email(
                    recipient, 
                    kwargs.get('firstname', ''), 
                    kwargs.get('verification_token', '')
                )
            elif email_type == "thank_you":
                await email_service.send_thank_you_email(
                    recipient,
                    kwargs.get('customer_name', ''),
                    kwargs.get('order_number', '')
                )
            elif email_type == "review_request":
                await email_service.send_review_request_email(
                    recipient,
                    kwargs.get('customer_name', ''),
                    kwargs.get('order_number', '')
                )
            elif email_type == "order_confirmation":
                await email_service.send_order_confirmation_email(
                    recipient,
                    kwargs.get('customer_name', ''),
                    kwargs.get('order_number', ''),
                    kwargs.get('order_date', datetime.now()),
                    kwargs.get('total_amount', 0.0),
                    kwargs.get('items', []),
                    kwargs.get('shipping_address', {})
                )
            elif email_type == "password_reset":
                await email_service.send_password_reset_email(
                    recipient, kwargs.get('reset_token', ''), kwargs.get('reset_link', '')
                )
            elif email_type == "low_stock_alert":
                await email_service.send_low_stock_alert(
                    recipient,
                    kwargs.get('product_name', ''),
                    kwargs.get('variant_name', ''),
                    kwargs.get('location_name', ''),
                    kwargs.get('current_stock', 0),
                    kwargs.get('threshold', 0)
                )
            elif email_type == "shipping_update":
                await email_service.send_shipping_update_email(
                    recipient,
                    kwargs.get('customer_name', ''),
                    kwargs.get('order_number', ''),
                    kwargs.get('tracking_number', ''),
                    kwargs.get('carrier', ''),
                    kwargs.get('estimated_delivery'),
                    kwargs.get('tracking_url')
                )
            elif email_type == "order_delivered":
                await email_service.send_order_delivered_email(
                    recipient,
                    kwargs.get('customer_name', ''),
                    kwargs.get('order_id', ''),
                    kwargs.get('order_number', ''),
                    kwargs.get('tracking_number', ''),
                    kwargs.get('delivery_date', datetime.now()),
                    kwargs.get('delivery_address', ''),
                    kwargs.get('delivery_notes')
                )
            else:
                print(f"⚠️ Unknown email type: {email_type}")
                return f"unknown: {email_type}"

        return f"sent: {email_type} → {recipient}"
    except Exception as e:
        print(f"❌ Email task failed ({email_type} → {recipient}): {e}")
        raise


# ============================================================================
# SUBSCRIPTION TASKS
# ============================================================================

async def process_subscription_orders_task() -> str:
    """Process due subscription orders."""
    try:
        import core.db as core_db
        if not hasattr(core_db, 'db_manager') or not core_db.db_manager:
            return "failed: db not initialized"
        
        from services.commerce.subscriptions_scheduler import SubscriptionScheduler
        
        # Use simple session without retry wrapper for scheduled tasks
        session_factory = core_db.db_manager.session_factory
        if not session_factory:
            return "failed: no session factory"
        
        async with session_factory() as db:
            scheduler = SubscriptionScheduler(db)
            result = await scheduler.process_due_subscriptions()
            return f"subscriptions: {result.get('processed_count', 0)} ok, {result.get('failed_count', 0)} failed"
            
    except Exception as e:
        print(f"❌ Subscription task failed: {e}")
        raise


# ============================================================================
# PROMOCODE TASKS
# ============================================================================

async def update_promocode_statuses_task() -> str:
    """Update promocode statuses."""
    try:
        import core.db as core_db
        if not hasattr(core_db, 'db_manager') or not core_db.db_manager:
            return "failed: db not initialized"
        
        from services.commerce.promocode_scheduler import PromoCodeScheduler
        
        # Use simple session without retry wrapper for scheduled tasks
        session_factory = core_db.db_manager.session_factory
        if not session_factory:
            return "failed: no session factory"
        
        async with session_factory() as db:
            scheduler = PromoCodeScheduler(db)
            result = await scheduler.update_promocode_statuses()
            return f"promocodes: {result.get('activated_count', 0)} activated, {result.get('deactivated_count', 0)} deactivated"
            
    except Exception as e:
        print(f"❌ Promocode task failed: {e}")
        raise


# ============================================================================
# SCHEDULER — runs periodic jobs using asyncio
# ============================================================================

async def _run_scheduler():
    """Lightweight asyncio scheduler — replaces ARQ cron jobs."""
    print("🕐 Background scheduler started")
    last_subscription_run: datetime | None = None
    last_promocode_run: datetime | None = None

    while True:
        now = datetime.now()

        # Subscriptions: every 6 hours at 2, 8, 14, 20
        if now.hour in {2, 8, 14, 20} and now.minute == 0:
            if last_subscription_run is None or (now - last_subscription_run).total_seconds() > 3600:
                last_subscription_run = now
                try:
                    result = await process_subscription_orders_task()
                    print(f"✅ {result}")
                except Exception as e:
                    print(f"❌ Subscription scheduler error: {e}")

        # Promocodes: daily at midnight
        if now.hour == 0 and now.minute == 0:
            if last_promocode_run is None or (now - last_promocode_run).total_seconds() > 3600:
                last_promocode_run = now
                try:
                    result = await update_promocode_statuses_task()
                    print(f"✅ {result}")
                except Exception as e:
                    print(f"❌ Promocode scheduler error: {e}")

        await asyncio.sleep(60)  # check every minute


def start_scheduler():
    """Start the asyncio scheduler as a background task."""
    loop = asyncio.get_event_loop()
    loop.create_task(_run_scheduler())
    print("✅ Background scheduler registered")


# ============================================================================
# COMPAT STUBS — so existing callers don't break
# ============================================================================

async def enqueue_subscription_renewal(subscription_id: str, **kwargs):
    await process_subscription_orders_task()

async def enqueue_subscription_processing():
    await process_subscription_orders_task()

async def enqueue_cart_cleanup():
    pass  # No-op without Redis TTL

async def enqueue_promocode_update():
    await update_promocode_statuses_task()

async def enqueue_sync_product_availability(product_id: str = None):
    session = _get_db_session()
    if not session:
        return
    
    try:
        from services.catalog.inventory import InventoryService
        from uuid import UUID
        async with session as db:
            svc = InventoryService(db, None)
            await svc.sync(UUID(product_id) if product_id else None)
    except Exception as e:
        print(f"❌ Availability sync failed: {e}")
