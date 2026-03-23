"""
Painless refund service with automatic processing and intelligent approval
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from uuid import UUID
from core.utils.uuid_utils import uuid7
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc
from sqlalchemy.orm import selectinload
from fastapi import HTTPException

from models.refunds import Refund, RefundItem, RefundStatus, RefundReason, RefundType
from models.orders import Order, OrderItem
from models.payments import Transaction
from models.user import User
from schemas.refunds import RefundRequest, RefundResponse, RefundItemRequest
from core.config import settings
from core.logging import get_structured_logger
import stripe

logger = get_structured_logger(__name__)


class RefundService:
    """Painless refund service with intelligent automation"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def request_refund(
        self,
        user_id: UUID,
        order_id: UUID,
        refund_request: RefundRequest
    ) -> RefundResponse:
        """
        Request a refund with intelligent processing
        Automatically approves eligible refunds for faster processing
        """
        try:
            # Validate order and user
            order = await self._get_user_order(user_id, order_id)
            
            # Check refund eligibility
            eligibility = await self._check_refund_eligibility(order)
            if not eligibility["eligible"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Order not eligible for refund: {eligibility['reason']}"
                )
            
            # Generate refund number
            refund_number = await self._generate_refund_number()
            
            # Calculate refund amounts
            refund_calculation = await self._calculate_refund_amounts(
                order, refund_request.items
            )
            
            # Create refund record
            refund = Refund(
                id=uuid7(), 
                order_id=order_id,
                user_id=user_id,
                refund_number=refund_number,
                status=RefundStatus.REQUESTED,
                refund_type=refund_request.refund_type,
                reason=refund_request.reason,
                requested_amount=refund_calculation["total_amount"],
                currency=order.currency,
                customer_reason=refund_request.customer_reason,
                customer_notes=refund_request.customer_notes,
                requires_return=self._requires_return(refund_request.reason),
                refund_metadata={
                    "request_source": "customer_portal",
                    "order_age_days": (datetime.now(timezone.utc) - order.created_at).days,
                    "original_order_amount": float(order.total_amount)
                }
            )
            
            self.db.add(refund)
            await self.db.flush()  # Get refund ID
            
            # Create refund items
            for item_request in refund_request.items:
                refund_item = RefundItem(
                    refund_id=refund.id,
                    order_item_id=item_request.order_item_id,
                    quantity_to_refund=item_request.quantity,
                    unit_price=refund_calculation["items"][str(item_request.order_item_id)]["unit_price"],
                    total_refund_amount=refund_calculation["items"][str(item_request.order_item_id)]["total_amount"],
                    condition_notes=item_request.condition_notes
                )
                self.db.add(refund_item)
            
            # Check for automatic approval
            if refund.is_eligible_for_auto_approval:
                await self._auto_approve_refund(refund)
            
            await self.db.commit()
            await self.db.refresh(refund)
            

            
            # Send refund events using ARQ
            
            return await self._format_refund_response(refund)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to request refund: {e}")
            raise HTTPException(status_code=500, detail="Failed to process refund request")
    
    async def process_automatic_refunds(self) -> Dict[str, Any]:
        """
        Process pending automatic refunds
        Called by background job to handle auto-approved refunds
        """
        try:
            # Get auto-approved refunds that need processing
            pending_refunds = await self.db.execute(
                select(Refund)
                .where(
                    and_(
                        Refund.status == RefundStatus.APPROVED,
                        Refund.auto_approved == True,
                        Refund.processed_at.is_(None)
                    )
                )
                .options(selectinload(Refund.order))
                .limit(50)  # Process in batches
            )
            
            refunds = pending_refunds.scalars().all()
            processed_count = 0
            failed_count = 0
            
            for refund in refunds:
                try:
                    await self._process_stripe_refund(refund)
                    processed_count += 1
                except Exception as e:
                    logger.error(f"Failed to process automatic refund {refund.id}: {e}")
                    failed_count += 1
            
            await self.db.commit()
            
            return {
                "processed": processed_count,
                "failed": failed_count,
                "total": len(refunds)
            }
            
        except Exception as e:
            logger.error(f"Failed to process automatic refunds: {e}")
            return {"processed": 0, "failed": 0, "total": 0, "error": str(e)}
    
    async def get_user_refunds(
        self,
        user_id: UUID,
        status: Optional[RefundStatus] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[RefundResponse]:
        """Get user's refund history"""
        try:
            query = select(Refund).where(Refund.user_id == user_id)
            
            if status:
                query = query.where(Refund.status == status)
            
            query = query.options(
                selectinload(Refund.order),
                selectinload(Refund.refund_items).selectinload(RefundItem.order_item)
            ).order_by(desc(Refund.created_at)).limit(limit).offset(offset)
            
            result = await self.db.execute(query)
            refunds = result.scalars().all()
            
            return [await self._format_refund_response(refund) for refund in refunds]
            
        except Exception as e:
            logger.error(f"Failed to get user refunds: {e}")
            raise HTTPException(status_code=500, detail="Failed to retrieve refunds")
    
    async def get_refund_details(self, user_id: UUID, refund_id: UUID) -> RefundResponse:
        """Get detailed refund information"""
        try:
            refund = await self.db.execute(
                select(Refund)
                .where(and_(Refund.id == refund_id, Refund.user_id == user_id))
                .options(
                    selectinload(Refund.order),
                    selectinload(Refund.refund_items).selectinload(RefundItem.order_item)
                )
            )
            refund = refund.scalar_one_or_none()
            
            if not refund:
                raise HTTPException(status_code=404, detail="Refund not found")
            
            return await self._format_refund_response(refund)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get refund details: {e}")
            raise HTTPException(status_code=500, detail="Failed to retrieve refund details")
    
    async def cancel_refund(self, user_id: UUID, refund_id: UUID) -> RefundResponse:
        """Cancel a pending refund request"""
        try:
            refund = await self.db.execute(
                select(Refund)
                .where(and_(Refund.id == refund_id, Refund.user_id == user_id))
                .options(selectinload(Refund.order))
            )
            refund = refund.scalar_one_or_none()
            
            if not refund:
                raise HTTPException(status_code=404, detail="Refund not found")
            
            if refund.status not in [RefundStatus.REQUESTED, RefundStatus.PENDING_REVIEW]:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot cancel refund in current status"
                )
            
            refund.status = RefundStatus.CANCELLED
            await self.db.commit()
            
            # Send notification
            await self._send_refund_notifications(refund, "cancelled")
            
            return await self._format_refund_response(refund)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to cancel refund: {e}")
            raise HTTPException(status_code=500, detail="Failed to cancel refund")
    
    async def _get_user_order(self, user_id: UUID, order_id: UUID) -> Order:
        """Get and validate user's order"""
        order = await self.db.execute(
            select(Order)
            .where(and_(Order.id == order_id, Order.user_id == user_id))
            .options(selectinload(Order.order_items))
        )
        order = order.scalar_one_or_none()
        
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        return order
    
    async def _check_refund_eligibility(self, order: Order) -> Dict[str, Any]:
        """Check if order is eligible for refund"""
        # Check order status
        if order.order_status not in ["confirmed", "shipped", "delivered"]:
            return {
                "eligible": False,
                "reason": "Order must be confirmed, shipped, or delivered to request refund"
            }
        
        # Check if order is too old (90 days limit)
        order_age = (datetime.now(timezone.utc) - order.created_at).days
        if order_age > 90:
            return {
                "eligible": False,
                "reason": "Refund window has expired (90 days limit)"
            }
        
        # Check if refund already exists
        existing_refund = await self.db.execute(
            select(Refund)
            .where(
                and_(
                    Refund.order_id == order.id,
                    Refund.status.in_([
                        RefundStatus.REQUESTED,
                        RefundStatus.PENDING_REVIEW,
                        RefundStatus.APPROVED,
                        RefundStatus.PROCESSING
                    ])
                )
            )
        )
        
        if existing_refund.scalar_one_or_none():
            return {
                "eligible": False,
                "reason": "A refund request already exists for this order"
            }
        
        return {"eligible": True, "reason": None}
    
    async def _calculate_refund_amounts(
        self,
        order: Order,
        refund_items: List[RefundItemRequest]
    ) -> Dict[str, Any]:
        """Calculate refund amounts for requested items"""
        calculation = {
            "items": {},
            "total_amount": 0.0,
            "shipping_refund": 0.0,
            "tax_refund": 0.0
        }
        
        # Get order items
        order_items_map = {str(item.id): item for item in order.order_items}
        
        for refund_item in refund_items:
            order_item_id = str(refund_item.order_item_id)
            
            if order_item_id not in order_items_map:
                raise HTTPException(
                    status_code=400,
                    detail=f"Order item {order_item_id} not found"
                )
            
            order_item = order_items_map[order_item_id]
            
            # Validate quantity
            if refund_item.quantity > order_item.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot refund more items than ordered"
                )
            
            # Calculate refund amount
            unit_price = float(order_item.price_per_unit)
            total_amount = unit_price * refund_item.quantity
            
            calculation["items"][order_item_id] = {
                "unit_price": unit_price,
                "quantity": refund_item.quantity,
                "total_amount": total_amount
            }
            
            calculation["total_amount"] += total_amount
        
        # Calculate proportional shipping refund (if full order refund)
        total_order_items = sum(item.quantity for item in order.order_items)
        total_refund_items = sum(item.quantity for item in refund_items)
        
        if total_refund_items == total_order_items:
            # Full refund - include shipping
            calculation["shipping_refund"] = float(order.shipping_cost or 0)
            calculation["total_amount"] += calculation["shipping_refund"]
        
        # Calculate proportional tax refund
        if order.tax_amount:
            tax_rate = float(order.tax_amount) / float(order.subtotal)
            calculation["tax_refund"] = calculation["total_amount"] * tax_rate
            calculation["total_amount"] += calculation["tax_refund"]
        
        return calculation
    
    async def _generate_refund_number(self) -> str:
        """Generate unique refund number"""
        import random
        import string
        
        while True:
            # Generate REF-XXXXXXXX format
            suffix = ''.join(random.choices(string.digits, k=8))
            refund_number = f"REF-{suffix}"
            
            # Check if already exists
            existing = await self.db.execute(
                select(Refund).where(Refund.refund_number == refund_number)
            )
            
            if not existing.scalar_one_or_none():
                return refund_number
    
    def _requires_return(self, reason: RefundReason) -> bool:
        """Determine if refund requires item return"""
        no_return_reasons = [
            RefundReason.DEFECTIVE_PRODUCT,
            RefundReason.DAMAGED_IN_SHIPPING,
            RefundReason.WRONG_ITEM,
            RefundReason.MISSING_PARTS
        ]
        return reason not in no_return_reasons
    
    async def _auto_approve_refund(self, refund: Refund):
        """Automatically approve eligible refunds with inventory restoration"""
        refund.status = RefundStatus.APPROVED
        refund.auto_approved = True
        refund.approved_amount = refund.requested_amount
        refund.approved_at = datetime.now(timezone.utc)
        
        # Restore inventory for refunded items
        await self._restore_inventory_for_refund(refund)
        
        logger.info(f"Auto-approved refund {refund.refund_number} for ${refund.requested_amount}")
    
    async def _restore_inventory_for_refund(self, refund: Refund):
        """Restore inventory when refund is confirmed"""
        try:
            from services.inventory import InventoryService
            
            inventory_service = InventoryService(self.db)
            
            # Get refund items with order item details
            refund_items = await self.db.execute(
                select(RefundItem)
                .options(selectinload(RefundItem.order_item))
                .where(RefundItem.refund_id == refund.id)
            )
            refund_items = refund_items.scalars().all()
            
            for refund_item in refund_items:
                try:
                    # Restore inventory for each refunded item
                    restore_result = await inventory_service.increment_stock_on_cancellation(
                        variant_id=refund_item.order_item.variant_id,
                        quantity=refund_item.quantity_to_refund,
                        location_id=None,  # Will be determined by service
                        order_id=refund.order_id,
                        user_id=refund.user_id
                    )
                    
                    logger.info(f"Restored {refund_item.quantity_to_refund} units of variant {refund_item.order_item.variant_id} for refund {refund.refund_number}")
                    
                except Exception as restore_error:
                    logger.error(f"Failed to restore inventory for refund item {refund_item.id}: {restore_error}")
                    # Continue with other items even if one fails
                    
        except Exception as e:
            logger.error(f"Failed to restore inventory for refund {refund.id}: {e}")
            # Don't fail the refund if inventory restoration fails
    
    async def _process_stripe_refund(self, refund: Refund):
        """Process refund through Stripe"""
        try:
            # Get original payment transaction
            transaction = await self.db.execute(
                select(Transaction)
                .where(
                    and_(
                        Transaction.order_id == refund.order_id,
                        Transaction.status == "succeeded",
                        Transaction.transaction_type == "payment"
                    )
                )
            )
            transaction = transaction.scalar_one_or_none()
            
            if not transaction or not transaction.stripe_payment_intent_id:
                raise Exception("Original payment transaction not found")
            
            # Create Stripe refund
            stripe_refund = stripe.Refund.create(
                payment_intent=transaction.stripe_payment_intent_id,
                amount=int(refund.approved_amount * 100),  # Convert to cents
                reason="requested_by_customer",
                metadata={
                    "refund_id": str(refund.id),
                    "order_id": str(refund.order_id),
                    "refund_number": refund.refund_number
                }
            )
            
            # Update refund record
            refund.status = RefundStatus.PROCESSING
            refund.stripe_refund_id = stripe_refund.id
            refund.stripe_status = stripe_refund.status
            refund.processed_at = datetime.now(timezone.utc)
            refund.processed_amount = refund.approved_amount
            
            # If Stripe refund is immediate, mark as completed
            if stripe_refund.status == "succeeded":
                refund.status = RefundStatus.COMPLETED
                refund.completed_at = datetime.now(timezone.utc)
            
            # Send notification
            await self._send_refund_notifications(refund, "processed")
            
            logger.info(f"Processed Stripe refund {stripe_refund.id} for refund {refund.refund_number}")
            
        except Exception as e:
            refund.status = RefundStatus.FAILED
            refund.admin_notes = f"Stripe processing failed: {str(e)}"
            logger.error(f"Failed to process Stripe refund for {refund.refund_number}: {e}")
            raise
    
    async def _send_refund_notifications(self, refund: Refund, event_type: str):
        """Send refund notifications to customer"""
        try:
            # This would integrate with your notification service
            notification_data = {
                "user_id": str(refund.user_id),
                "refund_number": refund.refund_number,
                "amount": refund.requested_amount,
                "status": refund.status.value,
                "event_type": event_type
            }
            
            # Send refund notifications using ARQ
            
        except Exception as e:
            logger.error(f"Failed to send refund notification: {e}")
    
    async def _format_refund_response(self, refund: Refund) -> RefundResponse:
        """Format refund for API response"""
        return RefundResponse(
            id=refund.id,
            order_id=refund.order_id,
            refund_number=refund.refund_number,
            status=refund.status,
            refund_type=refund.refund_type,
            reason=refund.reason,
            requested_amount=refund.requested_amount,
            approved_amount=refund.approved_amount,
            processed_amount=refund.processed_amount,
            currency=refund.currency,
            customer_reason=refund.customer_reason,
            customer_notes=refund.customer_notes,
            auto_approved=refund.auto_approved,
            requires_return=refund.requires_return,
            return_shipping_paid=refund.return_shipping_paid,
            requested_at=refund.requested_at,
            approved_at=refund.approved_at,
            processed_at=refund.processed_at,
            completed_at=refund.completed_at,
            items=[
                {
                    "order_item_id": item.order_item_id,
                    "quantity": item.quantity_to_refund,
                    "amount": item.total_refund_amount,
                    "condition_notes": item.condition_notes
                }
                for item in refund.refund_items
            ] if refund.refund_items else [],
            timeline=self._generate_refund_timeline(refund)
        )
    
    async def get_user_refunds_count(
        self,
        user_id: UUID,
        status: Optional[RefundStatus] = None
    ) -> int:
        """Get count of user's refunds"""
        try:
            query = select(Refund).where(Refund.user_id == user_id)
            
            if status:
                query = query.where(Refund.status == status)
            
            result = await self.db.execute(query)
            refunds = result.scalars().all()
            
            return len(refunds)
            
        except Exception as e:
            logger.error(f"Failed to get user refunds count: {e}")
            return 0
    
    async def get_user_refund_stats(self, user_id: UUID) -> Dict[str, Any]:
        """Get user's refund statistics"""
        try:
            # Get all user refunds
            refunds = await self.get_user_refunds(user_id)
            
            stats = {
                "total_refunds": len(refunds),
                "total_refunded_amount": sum(r.processed_amount or 0 for r in refunds),
                "by_status": {},
                "by_reason": {},
                "average_processing_time_days": 0
            }
            
            # Count by status
            for refund in refunds:
                status_key = refund.status.value if refund.status else "unknown"
                stats["by_status"][status_key] = stats["by_status"].get(status_key, 0) + 1
            
            # Count by reason
            for refund in refunds:
                reason_key = refund.reason.value if refund.reason else "unknown"
                stats["by_reason"][reason_key] = stats["by_reason"].get(reason_key, 0) + 1
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get user refund stats: {e}")
            return {
                "total_refunds": 0,
                "total_refunded_amount": 0.0,
                "by_status": {},
                "by_reason": {},
                "average_processing_time_days": 0
            }
    
    async def check_order_refund_eligibility(
        self,
        user_id: UUID,
        order_id: UUID
    ) -> Dict[str, Any]:
        """Check if order is eligible for refund"""
        try:
            order = await self._get_user_order(user_id, order_id)
            eligibility = await self._check_refund_eligibility(order)
            
            return {
                "eligible": eligibility["eligible"],
                "reason": eligibility["reason"],
                "order_id": str(order_id),
                "order_date": order.created_at.isoformat(),
                "order_amount": float(order.total_amount),
                "refund_window_days": 90,
                "days_remaining": max(0, 90 - (datetime.now(timezone.utc) - order.created_at).days)
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to check order refund eligibility: {e}")
            return {
                "eligible": False,
                "reason": "Unable to check eligibility",
                "order_id": str(order_id),
                "order_date": None,
                "order_amount": 0.0,
                "refund_window_days": 90,
                "days_remaining": 0
            }
    
    def _generate_refund_timeline(self, refund: Refund) -> List[Dict[str, Any]]:
        """Generate refund timeline for customer"""
        timeline = []
        
        if refund.requested_at:
            timeline.append({
                "status": "requested",
                "title": "Refund Requested",
                "description": "Your refund request has been submitted",
                "timestamp": refund.requested_at.isoformat(),
                "completed": True
            })
        
        if refund.auto_approved:
            timeline.append({
                "status": "approved",
                "title": "Automatically Approved",
                "description": "Your refund was automatically approved and is being processed",
                "timestamp": refund.approved_at.isoformat() if refund.approved_at else None,
                "completed": True
            })
        elif refund.status in [RefundStatus.PENDING_REVIEW, RefundStatus.APPROVED]:
            timeline.append({
                "status": "review",
                "title": "Under Review",
                "description": "Our team is reviewing your refund request",
                "timestamp": None,
                "completed": refund.status != RefundStatus.PENDING_REVIEW
            })
        
        if refund.processed_at:
            timeline.append({
                "status": "processing",
                "title": "Processing Refund",
                "description": f"Refund of ${refund.processed_amount:.2f} is being processed",
                "timestamp": refund.processed_at.isoformat(),
                "completed": True
            })
        
        if refund.completed_at:
            timeline.append({
                "status": "completed",
                "title": "Refund Completed",
                "description": "Your refund has been processed and should appear in your account within 3-5 business days",
                "timestamp": refund.completed_at.isoformat(),
                "completed": True
            })
        
        return timeline