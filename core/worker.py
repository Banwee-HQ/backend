"""Background task worker (ARQ/Redis removed): asyncio for scheduled jobs, BackgroundTasks for one-off tasks."""
import asyncio
from datetime import datetime
from uuid import UUID
import core.db as core_db
from core.logging import get_structured_logger
from services.accounts.email import EmailService
from services.commerce.subscriptions_scheduler import SubscriptionScheduler
from services.commerce.promocode_scheduler import PromoCodeScheduler

logger = get_structured_logger(__name__)


def _get_retrying_db_session():
    """Return the app's retry-wrapped DB session context manager, or None if the app isn't initialized."""
    try:
        if hasattr(core_db, 'db_manager') and core_db.db_manager:
            return core_db.db_manager.get_session_with_retry()
    except Exception:
        pass
    return None


def _get_plain_session_factory():
    """Return the app's plain (non-retrying) session factory, or None if the app isn't initialized."""
    if not hasattr(core_db, 'db_manager') or not core_db.db_manager:
        return None
    return core_db.db_manager.session_factory


# --- Email tasks ---

async def send_email_task(email_type: str, recipient: str, **kwargs) -> str:
    session = _get_retrying_db_session()
    if not session:
        logger.error(f"DB session not available for email task ({email_type})")
        return "failed"

    try:
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
                logger.warning(f"Unknown email type: {email_type}")
                return f"unknown: {email_type}"

        return f"sent: {email_type} → {recipient}"
    except Exception as e:
        logger.error(f"Email task failed ({email_type} → {recipient}): {e}")
        raise


# --- Scheduled jobs (subscriptions, promocodes) ---

async def _run_scheduled_job(job_name: str, run_job) -> str:
    """Open a plain DB session (not the retrying one - a job every few hours can just
    wait for the next tick) and run one scheduled job, with a consistent failure message."""
    session_factory = _get_plain_session_factory()
    if session_factory is None:
        return "failed: db not initialized"

    try:
        async with session_factory() as db:
            return await run_job(db)
    except Exception as e:
        logger.error(f"{job_name} task failed: {e}")
        raise


async def process_subscription_orders_task() -> str:
    """Process due subscription orders."""
    async def run(db):
        result = await SubscriptionScheduler(db).process_due_subscriptions()
        return f"subscriptions: {result.get('processed_count', 0)} ok, {result.get('failed_count', 0)} failed"

    return await _run_scheduled_job("Subscription", run)


async def update_promocode_statuses_task() -> str:
    """Activate/deactivate promocodes whose validity window has started or ended."""
    async def run(db):
        result = await PromoCodeScheduler(db).update_promocode_statuses()
        return f"promocodes: {result.get('activated_count', 0)} activated, {result.get('deactivated_count', 0)} deactivated"

    return await _run_scheduled_job("Promocode", run)


# --- Scheduler loop ---

SUBSCRIPTION_RUN_HOURS = {2, 8, 14, 20}  # every 6 hours

async def expire_unverified_orders_task() -> str:
    """Release checkouts whose 3-D Secure verification was never finished."""
    async def run(db):
        from services.commerce.orders import OrderService
        return f"Released {await OrderService(db).expire_unverified_orders()} unverified orders"
    return await _run_scheduled_job("expire_unverified_orders", run)


async def _run_scheduler():
    """Check once a minute whether it's time to run the subscription or promocode job."""
    logger.info("Background scheduler started")
    last_subscription_run: datetime | None = None
    last_promocode_run: datetime | None = None

    while True:
        now = datetime.now()

        if now.hour in SUBSCRIPTION_RUN_HOURS and now.minute == 0:
            if last_subscription_run is None or (now - last_subscription_run).total_seconds() > 3600:
                last_subscription_run = now
                try:
                    logger.info(await process_subscription_orders_task())
                except Exception as e:
                    logger.error(f"Subscription scheduler error: {e}")

        if now.hour == 0 and now.minute == 0:
            if last_promocode_run is None or (now - last_promocode_run).total_seconds() > 3600:
                last_promocode_run = now
                try:
                    logger.info(await update_promocode_statuses_task())
                except Exception as e:
                    logger.error(f"Promocode scheduler error: {e}")

        if now.minute % 10 == 0:
            try:
                logger.info(await expire_unverified_orders_task())
            except Exception as e:
                logger.error(f"Unverified order expiry error: {e}")

        await asyncio.sleep(60)


def start_scheduler():
    """Start the asyncio scheduler as a background task. Must be called from a running event loop."""
    loop = asyncio.get_running_loop()
    loop.create_task(_run_scheduler())
    logger.info("Background scheduler registered")


# --- Compat stubs, so existing callers don't break ---

async def enqueue_subscription_renewal(subscription_id: str, **kwargs):
    await process_subscription_orders_task()

async def enqueue_cart_cleanup():
    pass  # No-op without Redis TTL

async def enqueue_promocode_update():
    await update_promocode_statuses_task()

async def enqueue_sync_product_availability(product_id: str = None):
    session = _get_retrying_db_session()
    if not session:
        return

    try:
        # Local: services.catalog.inventory imports enqueue_sync_product_availability
        # from this module, so a top-level import here would be circular.
        from services.catalog.inventory import InventoryService
        async with session as db:
            svc = InventoryService(db, None)
            await svc.sync(UUID(product_id) if product_id else None)
    except Exception as e:
        logger.error(f"Availability sync failed: {e}")
