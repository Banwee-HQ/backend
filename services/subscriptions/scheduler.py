"""
Subscription Scheduler Service
Handles automatic creation of orders for periodic shipments
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from uuid import UUID
from core.utils.uuid_utils import uuid7
from core.logging import get_structured_logger

from models.subscriptions import Subscription
from models.orders import Order, OrderItem, OrderStatus, PaymentStatus, FulfillmentStatus, OrderSource
from models.product import ProductVariant
from models.user import User, Address
from models.payments import PaymentMethod
from core.db import get_db

logger = get_structured_logger(__name__)


class SubscriptionScheduler:
    """Service for managing subscription billing and order creation"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def process_due_subscriptions(self) -> Dict[str, Any]:
        """Process all subscriptions that are due for billing"""
        current_time = datetime.now(timezone.utc)
        
        # Find active subscriptions due for billing OR due for retry
        result = await self.db.execute(
            select(Subscription).where(
                and_(
                    Subscription.status.in_(["active", "payment_failed"]),
                    or_(
                        # Regular billing
                        and_(
                            Subscription.next_billing_date <= current_time,
                            Subscription.auto_renew == True,
                            Subscription.status == "active"
                        ),
                        # Payment retry
                        and_(
                            Subscription.next_retry_date <= current_time,
                            Subscription.status == "payment_failed",
                            Subscription.payment_retry_count < 3
                        )
                    )
                )
            ).options(selectinload(Subscription.products))
        )
        
        due_subscriptions = result.scalars().all()
        
        processed_count = 0
        failed_count = 0
        results = []
        
        for subscription in due_subscriptions:
            try:
                result = await self.process_subscription(subscription)
                if result["success"]:
                    processed_count += 1
                    results.append({
                        "subscription_id": str(subscription.id),
                        "order_id": result["order_id"],
                        "order_number": result["order_number"],
                        "user_email": result["user_email"],
                        "status": "success"
                    })
                else:
                    failed_count += 1
                    results.append({
                        "subscription_id": str(subscription.id),
                        "status": "failed",
                        "reason": result.get("error", "Unknown error"),
                        "retry_count": subscription.payment_retry_count
                    })
            except Exception as e:
                failed_count += 1
                results.append({
                    "subscription_id": str(subscription.id),
                    "status": "failed",
                    "reason": str(e)
                })
                logger.error(f"Failed to process subscription {subscription.id}: {e}")
        
        return {
            "processed_count": processed_count,
            "failed_count": failed_count,
            "total_due": len(due_subscriptions),
            "results": results
        }
    
    async def process_subscription(self, subscription: Subscription) -> Dict[str, Any]:
        """Process a single subscription - payment first, then order"""
        try:
            # Get user
            user_result = await self.db.execute(
                select(User).where(User.id == subscription.user_id)
            )
            user = user_result.scalar_one_or_none()
            if not user:
                raise Exception(f"User not found for subscription {subscription.id}")
            
            # Get variants
            if not subscription.variant_ids:
                raise Exception(f"No products in subscription {subscription.id}")
            
            variant_uuids = [UUID(vid) for vid in subscription.variant_ids]
            variant_result = await self.db.execute(
                select(ProductVariant).where(
                    ProductVariant.id.in_(variant_uuids)
                ).options(selectinload(ProductVariant.product))
            )
            variants = variant_result.scalars().all()
            
            if not variants:
                raise Exception(f"No valid variants found for subscription {subscription.id}")
            
            # Recalculate current pricing
            from services.subscriptions.service import SubscriptionService
            subscription_service = SubscriptionService(self.db)
            pricing = await subscription_service.recalculate_current_pricing(subscription)
            
            # ========================================
            # STEP 1: PROCESS PAYMENT FIRST
            # ========================================
            from services.payments import PaymentService
            
            # Get user's default payment method
            payment_method_result = await self.db.execute(
                select(PaymentMethod).where(
                    and_(
                        PaymentMethod.user_id == subscription.user_id,
                        PaymentMethod.is_default == True
                    )
                )
            )
            payment_method = payment_method_result.scalar_one_or_none()
            
            if not payment_method:
                raise Exception(f"No default payment method found for user {subscription.user_id}")
            
            # Generate order number and ID
            order_number = await self._generate_order_number()
            order_id = uuid7()
            
            payment_service = PaymentService(self.db)
            payment_result = await payment_service.process_payment_idempotent(
                user_id=subscription.user_id,
                order_id=order_id,
                amount=pricing["total"],
                payment_method_id=payment_method.id,
                idempotency_key=f"subscription_{subscription.id}_{order_id}",
                request_id=str(order_id)
            )
            
            # Check payment status
            if payment_result.get("status") != "succeeded":
                error_message = payment_result.get("error", "Payment processing failed")
                
                # Update retry tracking
                subscription.payment_retry_count = (subscription.payment_retry_count or 0) + 1
                subscription.last_payment_attempt = datetime.now(timezone.utc)
                subscription.last_payment_error = error_message
                
                # Determine retry schedule
                if subscription.payment_retry_count == 1:
                    # First failure: retry in 6 hours
                    subscription.next_retry_date = datetime.now(timezone.utc) + timedelta(hours=6)
                    subscription.status = "payment_failed"
                    
                    logger.warning(f"Payment failed for subscription {subscription.id} (attempt 1/3). Retry in 6 hours.")
                    
                elif subscription.payment_retry_count == 2:
                    # Second failure: retry in 24 hours (next day)
                    subscription.next_retry_date = datetime.now(timezone.utc) + timedelta(hours=24)
                    subscription.status = "payment_failed"
                    
                    logger.warning(f"Payment failed for subscription {subscription.id} (attempt 2/3). Retry in 24 hours.")
                    
                else:
                    # Third failure: pause subscription
                    subscription.status = "paused"
                    subscription.paused_at = datetime.now(timezone.utc)
                    subscription.pause_reason = f"Payment failed after 3 attempts: {error_message}"
                    subscription.next_retry_date = None
                    
                    logger.error(f"Payment failed for subscription {subscription.id} (attempt 3/3). Subscription paused.")
                    
                    # Send email notification about paused subscription
                    try:
                        from services.email import EmailService
                        email_service = EmailService(self.db)
                        await email_service.send_subscription_payment_failed(
                            user_email=user.email,
                            subscription_id=str(subscription.id),
                            subscription_name=subscription.name,
                            error_message=error_message,
                            retry_count=subscription.payment_retry_count
                        )
                    except Exception as e:
                        logger.error(f"Failed to send payment failure email: {e}")
                
                await self.db.commit()
                
                return {
                    "success": False,
                    "error": error_message,
                    "retry_count": subscription.payment_retry_count,
                    "next_retry": subscription.next_retry_date.isoformat() if subscription.next_retry_date else None
                }
            
            logger.info(f"✅ Payment succeeded for subscription {subscription.id}, creating order...")
            
            # ========================================
            # STEP 2: CREATE ORDER (only after successful payment)
            # ========================================
            
            # Get shipping address
            shipping_address = await self._get_shipping_address(subscription)
            
            # Get quantities
            variant_quantities = subscription.subscription_metadata.get("variant_quantities", {}) if subscription.subscription_metadata else {}
            
            order = Order(
                id=order_id,
                user_id=subscription.user_id,
                order_number=order_number,
                order_status=OrderStatus.CONFIRMED,
                payment_status=PaymentStatus.PAID,
                fulfillment_status=FulfillmentStatus.UNFULFILLED,
                source=OrderSource.API,
                subtotal=pricing["subtotal"],
                tax_amount=pricing["tax"],
                shipping_cost=pricing["shipping"],
                discount_amount=pricing.get("discount", 0.0),
                total_amount=pricing["total"],
                currency=subscription.currency or "USD",
                shipping_method=subscription.delivery_type or "standard",
                shipping_address=shipping_address,
                billing_address=shipping_address,
                subscription_id=subscription.id
            )
            
            self.db.add(order)
            await self.db.flush()
            
            # ========================================
            # STEP 3: CREATE ORDER ITEMS
            # ========================================
            for variant_price in pricing["variant_prices"]:
                variant_id = UUID(variant_price["id"])
                variant = next((v for v in variants if v.id == variant_id), None)
                
                if variant:
                    qty = variant_price["qty"]
                    price = variant_price["price"]
                    
                    order_item = OrderItem(
                        order_id=order.id,
                        variant_id=variant.id,
                        quantity=qty,
                        price_per_unit=price,
                        total_price=price * qty
                    )
                    
                    self.db.add(order_item)
            
            await self.db.flush()
            
            # ========================================
            # STEP 4: UPDATE INVENTORY
            # ========================================
            from services.inventory import InventoryService
            from schemas.inventory import StockAdjustmentCreate
            
            inventory_service = InventoryService(self.db, None)
            
            for variant_price in pricing["variant_prices"]:
                variant_id = UUID(variant_price["id"])
                qty = variant_price["qty"]
                
                adjustment = StockAdjustmentCreate(
                    variant_id=variant_id,
                    quantity_change=-qty,
                    reason=f"Subscription order: {order.order_number}",
                    notes=f"Auto-adjusted for subscription {subscription.id}"
                )
                
                await inventory_service.adjust_stock(
                    adjustment,
                    adjusted_by_user_id=subscription.user_id,
                    commit=False
                )
            
            # ========================================
            # STEP 5: UPDATE SUBSCRIPTION
            # ========================================
            subscription.status = "active"
            subscription.last_payment_error = None
            subscription.payment_retry_count = 0  # Reset retry count on success
            subscription.last_payment_attempt = datetime.now(timezone.utc)
            subscription.next_retry_date = None
            
            # Update billing dates
            await self._update_billing_dates(subscription)
            
            await self.db.commit()
            
            logger.info(f"✅ Successfully created subscription order {order.order_number}")
            
            return {
                "success": True,
                "order_id": str(order.id),
                "order_number": order.order_number,
                "user_email": user.email
            }
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to process subscription {subscription.id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _generate_order_number(self) -> str:
        """Generate unique order number"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        short_uuid = str(uuid7())[:8].upper()
        return f"SUB-{timestamp}-{short_uuid}"
    
    async def _get_shipping_address(self, subscription: Subscription) -> Dict[str, Any]:
        """Get shipping address for subscription order"""
        if subscription.delivery_address_id:
            address_result = await self.db.execute(
                select(Address).where(Address.id == subscription.delivery_address_id)
            )
            address = address_result.scalar_one_or_none()
            if address:
                return {
                    "street": address.street,
                    "city": address.city,
                    "state": address.state,
                    "country": address.country,
                    "post_code": address.post_code,
                    "type": "shipping",
                    "delivery_type": subscription.delivery_type or "standard"
                }
        
        return {
            "type": "shipping",
            "delivery_type": subscription.delivery_type or "standard"
        }
    
    async def _update_billing_dates(self, subscription: Subscription):
        """Update subscription billing dates with proper month-end handling"""
        from dateutil.relativedelta import relativedelta
        
        current_period_end = subscription.current_period_end or datetime.now(timezone.utc)
        
        if subscription.billing_cycle == "weekly":
            next_period_end = current_period_end + timedelta(weeks=1)
            
        elif subscription.billing_cycle == "yearly":
            # Use relativedelta to handle leap years properly
            next_period_end = current_period_end + relativedelta(years=1)
            
        else:  # monthly (default)
            # Use relativedelta to handle month-end dates properly
            # This automatically handles 28, 29, 30, 31 day months
            next_period_end = current_period_end + relativedelta(months=1)
            
            # Example: Jan 31 + 1 month = Feb 28/29 (last day of Feb)
            # Example: Jan 30 + 1 month = Feb 28/29 (last day of Feb)
            # Example: Mar 31 + 1 month = Apr 30 (last day of Apr)
        
        subscription.current_period_start = current_period_end
        subscription.current_period_end = next_period_end
        subscription.next_billing_date = next_period_end
        
        # Update metadata
        if not subscription.subscription_metadata:
            subscription.subscription_metadata = {}
        
        subscription.subscription_metadata.update({
            "last_order_created": datetime.now(timezone.utc).isoformat(),
            "orders_created_count": subscription.subscription_metadata.get("orders_created_count", 0) + 1
        })
        
        logger.info(f"Updated billing dates for subscription {subscription.id}: next billing on {next_period_end.date()}")


# Standalone function for background task
async def process_subscription_shipments():
    """Background task function to process subscription shipments"""
    async for db in get_db():
        try:
            scheduler = SubscriptionScheduler(db)
            result = await scheduler.process_due_subscriptions()
            logger.info(f"Processed subscription shipments: {result}")
            return result
        except Exception as e:
            logger.error(f"Error processing subscription shipments: {e}")
            raise
        finally:
            await db.close()
