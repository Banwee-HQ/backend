"""
ARQ (Async Redis Queue) Worker Configuration
Handles background tasks: emails, subscriptions, and scheduled jobs
"""
import asyncio
from typing import Dict, Any
from datetime import datetime, timedelta
from arq import create_pool, Worker
from arq.connections import RedisSettings
from arq.cron import cron
from core.config import settings
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)

# ARQ Redis settings
ARQ_REDIS_SETTINGS = RedisSettings.from_dsn(settings.ARQ_REDIS_URL)


def _get_session_factory(ctx: Dict[str, Any]):
    """Resolve the current DB session factory from context or core.db manager."""
    factory = ctx.get('db_session')
    if factory:
        return factory

    try:
        import core.db as core_db
        if getattr(core_db, 'AsyncSessionDB', None):
            return core_db.AsyncSessionDB
        if getattr(core_db, 'db_manager', None) and getattr(core_db.db_manager, 'session_factory', None):
            return core_db.db_manager.session_factory
    except Exception:
        pass

    return None


async def startup(ctx: Dict[str, Any]) -> None:
    """Worker startup - initialize database connection"""
    logger.info("ARQ Worker starting up...")
    try:
        # Initialize database connection for ARQ worker
        from core.db import initialize_db, db_manager
        from core.config import settings
        
        # Initialize the database with the same settings as main app
        initialize_db(
            database_uri=settings.POSTGRES_DB_URL,
            env_is_local=settings.ENVIRONMENT == "local",
            use_optimized_engine=True
        )
        
        # Set the session factory from the db manager
        ctx['db_session'] = db_manager.session_factory
        logger.info("Database session factory initialized for ARQ worker")
    except Exception as e:
        logger.error(f"Failed to initialize database session factory: {e}")
        ctx['db_session'] = None

    try:
        pool = await create_pool(ARQ_REDIS_SETTINGS)
        ctx['arq_pool'] = pool
        logger.info("ARQ Redis pool initialized")
    except Exception as e:
        logger.warning(f"Failed to create ARQ pool in worker startup: {e}")
        ctx['arq_pool'] = None


async def shutdown(ctx: Dict[str, Any]) -> None:
    """Worker shutdown - cleanup resources"""
    logger.info("ARQ Worker shutting down...")
    try:
        pool = ctx.get('arq_pool')
        if pool is not None:
            await pool.close()
            logger.info("ARQ pool closed")
    except Exception as e:
        logger.warning(f"Error closing ARQ pool during shutdown: {e}")


# ============================================================================
# EMAIL TASKS - Only background task for checkout/orders
# ============================================================================

async def send_email_task(ctx: Dict[str, Any], email_type: str, recipient: str, **kwargs) -> str:
    """Send email background task"""
    try:
        from services.email import EmailService
        
        factory = _get_session_factory(ctx)
        if not factory:
            raise RuntimeError('Database session factory not available in ARQ context')

        async with factory() as db:
            email_service = EmailService(db)
            
            if email_type == "welcome":
                await email_service.send_welcome_email(
                    recipient, 
                    kwargs.get('user_name', '')
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
                    recipient, 
                    kwargs.get('reset_token', ''), 
                    kwargs.get('reset_link', '')
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
                return f"Unknown email type: {email_type}"
        
        logger.info(f"Email sent successfully: {email_type} to {recipient}")
        return f"Email sent: {email_type} to {recipient}"
        
    except Exception as e:
        logger.error(f"Failed to send email {email_type} to {recipient}: {e}")
        raise


# ============================================================================
# SUBSCRIPTION TASKS - Recurring order processing
# ============================================================================

async def process_subscription_renewal_task(ctx: Dict[str, Any], subscription_id: str, **kwargs) -> str:
    """Process subscription renewal background task"""
    try:
        from services.subscriptions.subscription_scheduler import SubscriptionSchedulerService
        from uuid import UUID
        
        factory = _get_session_factory(ctx)
        if not factory:
            raise RuntimeError('Database session factory not available in ARQ context')

        async with factory() as db:
            scheduler = SubscriptionSchedulerService(db)
            result = await scheduler.process_specific_subscription(UUID(subscription_id))
            
            if result.get('success'):
                # Send confirmation email
                await send_email_task(
                    ctx,
                    "order_confirmation",
                    kwargs.get('user_email', ''),
                    subscription_id=subscription_id,
                    order_id=result.get('order_id'),
                    **kwargs
                )
                return f"Subscription renewal completed for {subscription_id}"
            else:
                logger.error(f"Subscription renewal failed for {subscription_id}: {result.get('error')}")
                return f"Subscription renewal failed for {subscription_id}: {result.get('error')}"
                
    except Exception as e:
        logger.error(f"Error processing subscription renewal {subscription_id}: {e}")
        raise


async def process_subscription_orders_task(ctx: Dict[str, Any]) -> str:
    """Process all due subscription orders"""
    try:
        from services.subscriptions.scheduler import SubscriptionScheduler
        
        factory = _get_session_factory(ctx)
        if not factory:
            raise RuntimeError('Database session factory not available in ARQ context')

        async with factory() as db:
            scheduler = SubscriptionScheduler(db)
            result = await scheduler.process_due_subscriptions()
            
            # Send order confirmation emails for successful orders
            for order_result in result.get("results", []):
                if order_result["status"] == "success" and order_result.get("user_email"):
                    try:
                        # Get order details for email
                        from models.orders import Order
                        from sqlalchemy import select
                        from sqlalchemy.orm import selectinload
                        
                        order_query = await db.execute(
                            select(Order).where(Order.id == order_result["order_id"])
                            .options(selectinload(Order.items))
                        )
                        order = order_query.scalar_one_or_none()
                        
                        if order:
                            # Format items for email
                            email_items = []
                            for item in order.items:
                                email_items.append({
                                    "name": item.variant.name if hasattr(item, 'variant') and item.variant else "Item",
                                    "quantity": item.quantity,
                                    "price": float(item.price_per_unit or 0)
                                })
                            
                            # Send order confirmation email
                            await send_email_task(
                                ctx,
                                "order_confirmation",
                                order_result["user_email"],
                                customer_name="Customer",
                                order_number=order_result["order_number"],
                                order_date=order.created_at or datetime.now(),
                                total_amount=float(order.total_amount),
                                items=email_items,
                                shipping_address=order.shipping_address or {}
                            )
                            logger.info(f"Sent order confirmation email for subscription order {order_result['order_number']}")
                    except Exception as email_error:
                        logger.error(f"Failed to send email for order {order_result.get('order_id')}: {email_error}")
            
            return f"Processed {result.get('total_due', 0)} subscription orders: {result.get('processed_count', 0)} succeeded, {result.get('failed_count', 0)} failed"
            
    except Exception as e:
        logger.error(f"Error processing subscription orders: {e}")
        raise


# ============================================================================
# INVENTORY TASKS - Stock sync and alerts
# ============================================================================

async def sync_product_availability_task(ctx: Dict[str, Any], product_id: str = None) -> str:
    """Sync product availability status based on inventory levels"""
    try:
        from services.inventory import InventoryService
        from uuid import UUID
        
        factory = _get_session_factory(ctx)
        if not factory:
            raise RuntimeError('Database session factory not available in ARQ context')
        
        async with factory() as db:
            inventory_service = InventoryService(db, None)
            
            if product_id:
                # Sync single product
                result = await inventory_service.sync_product_availability_status(UUID(product_id))
                if result["success"]:
                    logger.info(f"✅ Synced product {product_id}: {result['old_status']} → {result['new_status']} (stock: {result['total_stock']})")
                    return f"Product {product_id} synced: {result['old_status']} → {result['new_status']}"
                else:
                    logger.warning(f"Failed to sync product {product_id}: {result['message']}")
                    return f"Failed to sync product {product_id}"
            else:
                # Sync all products
                result = await inventory_service.sync_all_products_availability()
                if result["success"]:
                    logger.info(f"✅ {result['message']}")
                    return result['message']
                else:
                    logger.warning(f"Failed to sync all products: {result['message']}")
                    return f"Failed to sync all products"
                
    except Exception as e:
        logger.error(f"Error syncing product availability: {e}")
        raise


# ============================================================================
# PROMOCODE TASKS - Scheduled status updates
# ============================================================================

async def update_promocode_statuses_task(ctx: Dict[str, Any]) -> str:
    """Update promocode statuses based on validity dates"""
    try:
        from services.promocode.scheduler import PromoCodeScheduler
        
        factory = _get_session_factory(ctx)
        if not factory:
            raise RuntimeError('Database session factory not available in ARQ context')

        async with factory() as db:
            scheduler = PromoCodeScheduler(db)
            result = await scheduler.update_promocode_statuses()
            
            if result.get("success"):
                logger.info(f"✅ Promocode status update completed: {result.get('activated_count', 0)} activated, {result.get('deactivated_count', 0)} deactivated")
                return f"Promocode update completed: {result.get('activated_count', 0)} activated, {result.get('deactivated_count', 0)} deactivated"
            else:
                logger.error(f"❌ Promocode status update failed: {result.get('error')}")
                return f"Promocode update failed: {result.get('error')}"
                
    except Exception as e:
        logger.error(f"Error updating promocode statuses: {e}")
        raise


# ============================================================================
# CLEANUP TASKS - Scheduled maintenance
# ============================================================================

async def cleanup_expired_carts_task(ctx: Dict[str, Any]) -> str:
    """Cleanup expired carts background task"""
    try:
        from core.cache import RedisService
        
        redis_service = RedisService()
        # Redis TTL handles cart expiration automatically
        logger.info("Expired carts cleanup task completed")
        return "Expired carts cleanup completed"
        
    except Exception as e:
        logger.error(f"Failed to cleanup expired carts: {e}")
        raise


# ============================================================================
# ARQ WORKER CONFIGURATION
# ============================================================================

class WorkerSettings:
    """ARQ Worker settings with cron jobs"""
    redis_settings = ARQ_REDIS_SETTINGS
    
    # Background task functions
    functions = [
        send_email_task,
        process_subscription_renewal_task,
        process_subscription_orders_task,
        update_promocode_statuses_task,
    ]
    
    # Cron jobs - Scheduled tasks that run automatically
    cron_jobs = [
        # Process subscription renewals and retries - runs every 6 hours
        # This catches both regular billing (2 AM) and retry attempts (6 hours, 24 hours)
        cron(
            process_subscription_orders_task,
            hour={2, 8, 14, 20},  # Run at 2 AM, 8 AM, 2 PM, 8 PM
            minute=0,
            run_at_startup=False,  # Don't run immediately on worker start
            unique=True,  # Prevent duplicate runs
            timeout=600,  # 10 minutes timeout
        ),
        
        # Update promocode statuses - runs daily at 12 AM (midnight)
        # Activates/deactivates promocodes based on validity dates and usage limits
        cron(
            update_promocode_statuses_task,
            hour=0,  # Run at 12 AM (midnight)
            minute=0,
            run_at_startup=False,  # Don't run immediately on worker start
            unique=True,  # Prevent duplicate runs
            timeout=300,  # 5 minutes timeout
        ),
    ]
    
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    job_timeout = 300  # 5 minutes default
    keep_result = 3600  # Keep results for 1 hour


# ============================================================================
# HELPER FUNCTIONS - For enqueueing jobs
# ============================================================================

async def get_arq_pool():
    """Get ARQ Redis pool for enqueueing jobs"""
    return await create_pool(ARQ_REDIS_SETTINGS)


async def enqueue_subscription_renewal(subscription_id: str, **kwargs):
    """Enqueue subscription renewal task"""
    pool = await get_arq_pool()
    await pool.enqueue_job('process_subscription_renewal_task', subscription_id, **kwargs)


async def enqueue_subscription_processing():
    """Enqueue subscription order processing task"""
    pool = await get_arq_pool()
    await pool.enqueue_job('process_subscription_orders_task')


async def enqueue_sync_product_availability(product_id: str = None):
    """Enqueue product availability sync task"""
    pool = await get_arq_pool()
    if product_id:
        await pool.enqueue_job('sync_product_availability_task', product_id)
    else:
        await pool.enqueue_job('sync_product_availability_task')


async def enqueue_cart_cleanup():
    """Enqueue cart cleanup task"""
    pool = await get_arq_pool()
    await pool.enqueue_job('cleanup_expired_carts_task')


async def enqueue_promocode_update():
    """Enqueue promocode status update task"""
    pool = await get_arq_pool()
    await pool.enqueue_job('update_promocode_statuses_task')
