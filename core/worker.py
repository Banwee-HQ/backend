"""Background jobs run inside the app: subscription renewals, promocode windows and abandoned bank checks."""
import asyncio
import time
from uuid import UUID

import core.db as core_db
from core.logging import get_structured_logger
from services.commerce.promocode_scheduler import PromoCodeScheduler
from services.commerce.subscriptions_scheduler import SubscriptionScheduler, renewal_lock

logger = get_structured_logger(__name__)

TICK_SECONDS = 30


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


async def _run_scheduled_job(job_name: str, run_job) -> str:
    """Run one job in its own DB session; errors are logged and re-raised."""
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
    """Renew due subscriptions and retry declined renewals, one process at a time."""
    async def run(db):
        async with renewal_lock(db) as acquired:
            if not acquired:
                return "subscriptions: skipped, another process is billing"
            scheduler = SubscriptionScheduler(db)
            result = await scheduler.process_due_subscriptions()
            reminders = await scheduler.send_upcoming_reminders()
        return (
            f"subscriptions: {result['paid']} paid, {result['declined']} declined, "
            f"{result['pending']} pending, {result['skipped']} skipped, {result['error']} errors, {reminders} reminders"
        )

    return await _run_scheduled_job("Subscription", run)


async def update_promocode_statuses_task() -> str:
    """Activate/deactivate promocodes whose validity window has started or ended."""
    async def run(db):
        result = await PromoCodeScheduler(db).update_promocode_statuses()
        return f"promocodes: {result.get('activated_count', 0)} activated, {result.get('deactivated_count', 0)} deactivated"

    return await _run_scheduled_job("Promocode", run)


async def expire_unverified_orders_task() -> str:
    """Release checkouts whose 3-D Secure verification was never finished."""
    async def run(db):
        from services.commerce.orders import OrderService
        return f"Released {await OrderService(db).expire_unverified_orders()} unverified orders"
    return await _run_scheduled_job("expire_unverified_orders", run)


# (job, seconds between runs). Each runs once at startup, so nothing waits on missed downtime.
JOBS = (
    (process_subscription_orders_task, 3600),
    (update_promocode_statuses_task, 3600),
    (expire_unverified_orders_task, 600),
)


async def _run_scheduler(jobs=JOBS, tick: float = TICK_SECONDS):
    """Run each job when its interval has passed; a failing job is logged and tried again next interval."""
    logger.info("Background scheduler started")
    next_run = {job: 0.0 for job, _ in jobs}
    while True:
        for job, interval in jobs:
            if time.monotonic() >= next_run[job]:
                next_run[job] = time.monotonic() + interval
                try:
                    logger.info(await job())
                except Exception as e:
                    logger.error(f"Scheduled job {job.__name__} failed: {e}")
        await asyncio.sleep(tick)


def start_scheduler():
    """Start the scheduler as a background task. Must be called from a running event loop."""
    asyncio.get_running_loop().create_task(_run_scheduler())
    logger.info("Background scheduler registered")


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
