"""Background task worker (ARQ/Redis removed): asyncio for scheduled jobs, BackgroundTasks for one-off tasks."""
import asyncio
from datetime import datetime
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)


def _get_retrying_db_session():
    """Return the app's retry-wrapped DB session context manager, or None if the app isn't initialized."""
    try:
        import core.db as core_db
        if hasattr(core_db, 'db_manager') and core_db.db_manager:
            return core_db.db_manager.get_session_with_retry()
    except Exception:
        pass
    return None


def _get_plain_session_factory():
    """Return the app's plain (non-retrying) session factory, or None if the app isn't initialized."""
    import core.db as core_db
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
                logger.warning(f"Unknown email type: {email_type}")
                return f"unknown: {email_type}"

        return f"sent: {email_type} → {recipient}"
    except Exception as e:
        logger.error(f"Email task failed ({email_type} → {recipient}): {e}")
        raise


# --- Scheduled jobs (subscriptions, promocodes) ---

async def _run_scheduled_job(job_name: str, run_job) -> str:
    """Open a plain DB session and run one scheduled job, with a consistent failure message.

    Scheduled jobs use a plain session rather than _get_retrying_db_session(): a job that
    runs every few hours can just wait for the next tick if the DB is briefly down, so the
    retry/backoff logic built for one-off, user-facing tasks isn't needed here.
    """
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
        from services.commerce.subscriptions_scheduler import SubscriptionScheduler
        result = await SubscriptionScheduler(db).process_due_subscriptions()
        return f"subscriptions: {result.get('processed_count', 0)} ok, {result.get('failed_count', 0)} failed"

    return await _run_scheduled_job("Subscription", run)


async def update_promocode_statuses_task() -> str:
    """Activate/deactivate promocodes whose validity window has started or ended."""
    async def run(db):
        from services.commerce.promocode_scheduler import PromoCodeScheduler
        result = await PromoCodeScheduler(db).update_promocode_statuses()
        return f"promocodes: {result.get('activated_count', 0)} activated, {result.get('deactivated_count', 0)} deactivated"

    return await _run_scheduled_job("Promocode", run)


# --- Scheduler loop ---

SUBSCRIPTION_RUN_HOURS = {2, 8, 14, 20}  # every 6 hours

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
        from services.catalog.inventory import InventoryService
        from uuid import UUID
        async with session as db:
            svc = InventoryService(db, None)
            await svc.sync(UUID(product_id) if product_id else None)
    except Exception as e:
        logger.error(f"Availability sync failed: {e}")
