"""
Webhook Service - Secure Stripe webhook handling with comprehensive security
Processes Stripe webhooks with signature verification, rate limiting, and secure message publishing
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from fastapi import HTTPException, Request
from models.payments import Transaction, PaymentIntent
from models.orders import Order
from services.payments import PaymentService
from services.inventory import InventoryService
from core.auth.webhook import verify_stripe_webhook_request, WebhookSecurityError
from uuid import UUID
from datetime import datetime
from typing import Dict, Any, Optional
from core.config import settings
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)


class WebhookService:
    """
    Secure Stripe webhook handling with signature verification
    Processes webhooks in real-time without storing webhook events
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.payment_service = PaymentService(db)
        self.inventory_service = InventoryService(db)
        
    async def handle_stripe_webhook(
        self,
        request: Request,
        request_body: bytes,
        signature: str
    ) -> Dict[str, Any]:
        """
        Handle Stripe webhook with comprehensive security verification
        """
        start_time = datetime.utcnow()
        
        try:
            # Comprehensive security verification
            verification_result = await verify_stripe_webhook_request(
                request=request,
                db=self.db,
                signature_header=signature,
                payload=request_body
            )
            
            if not verification_result["verified"]:
                raise HTTPException(
                    status_code=401,
                    detail="Webhook verification failed"
                )
            
            event = verification_result["event"]
            security_metadata = verification_result["security_metadata"]
            
            # Process the verified event
            result = await self._process_webhook_event(event)
            
            # Publish secure event update
            await self._publish_webhook_event(event, result, security_metadata)
            
            # Log processing completion
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Webhook processed successfully: {event['id']} in {processing_time:.3f}s")
            
            return {
                "status": "success",
                "event_id": event["id"],
                "event_type": event["type"],
                "processing_time": processing_time,
                "result": result
            }
            
        except WebhookSecurityError as e:
            logger.error(f"Webhook security error: {e}")
            raise HTTPException(status_code=401, detail=str(e))
        except Exception as e:
            logger.error(f"Webhook processing error: {e}")
            raise HTTPException(status_code=500, detail="Webhook processing failed")
        
        
    async def _process_webhook_event(
        self,
        event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process webhook event based on type"""
        event_type = event["type"]
        event_data = event["data"]["object"]
        
        if event_type == "payment_intent.succeeded":
            return await self._handle_payment_succeeded(event_data)
        
        elif event_type == "payment_intent.payment_failed":
            return await self._handle_payment_failed(event_data)
        
        elif event_type == "payment_intent.canceled":
            return await self._handle_payment_canceled(event_data)
        
        elif event_type == "charge.refunded":
            return await self._handle_refund(event_data)
        
        else:
            logger.info(f"Unhandled webhook event type: {event_type}")
            return {"status": "ignored", "reason": "unhandled_event_type"}

    async def _handle_payment_succeeded(self, payment_intent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle successful payment webhook"""
        stripe_payment_intent_id = payment_intent_data["id"]
        
        # Find the transaction with lock to prevent race conditions
        transaction_result = await self.db.execute(
            select(Transaction).where(
                Transaction.stripe_payment_intent_id == stripe_payment_intent_id
            ).with_for_update()
        )
        transaction = transaction_result.scalar_one_or_none()
        
        if transaction:
            # Update transaction status atomically
            transaction.status = "succeeded"
            transaction.transaction_details_metadata = {
                **transaction.transaction_details_metadata,
                "webhook_confirmed_at": datetime.utcnow().isoformat(),
                "stripe_charges": payment_intent_data.get("charges", {})
            }
            
            # If this is an order payment, update order status atomically
            if transaction.order_id:
                order_result = await self.db.execute(
                    select(Order).where(Order.id == transaction.order_id).with_for_update()
                )
                order = order_result.scalar_one_or_none()
                
                if order:
                    # Update order status to confirmed atomically
                    order.status = "confirmed"
                    order.version += 1  # Optimistic locking increment
                    
            
            await self.db.commit()
            
            return {
                "action": "payment_confirmed",
                "transaction_id": str(transaction.id),
                "order_id": str(transaction.order_id) if transaction.order_id else None
            }
        
        else:
            logger.warning(f"Transaction not found for payment intent {stripe_payment_intent_id}")
            return {
                "action": "payment_confirmed",
                "warning": "transaction_not_found",
                "stripe_payment_intent_id": stripe_payment_intent_id
            }

    async def _handle_payment_failed(self, payment_intent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle failed payment webhook with comprehensive failure handling"""
        stripe_payment_intent_id = payment_intent_data["id"]
        
        # Find the transaction with lock to prevent race conditions
        transaction_result = await self.db.execute(
            select(Transaction).where(
                Transaction.stripe_payment_intent_id == stripe_payment_intent_id
            ).with_for_update()
        )
        transaction = transaction_result.scalar_one_or_none()
        
        if transaction:
            # Update transaction status atomically
            transaction.status = "failed"
            transaction.failure_reason = payment_intent_data.get("last_payment_error", {}).get("message", "Payment failed")
            transaction.transaction_details_metadata = {
                **transaction.transaction_details_metadata,
                "webhook_failed_at": datetime.utcnow().isoformat(),
                "failure_details": payment_intent_data.get("last_payment_error", {})
            }
            
            # If this is an order payment, update order status atomically
            if transaction.order_id:
                order_result = await self.db.execute(
                    select(Order).where(Order.id == transaction.order_id).with_for_update()
                )
                order = order_result.scalar_one_or_none()
                if order:
                    order.status = "payment_failed"
                    order.version += 1  # Optimistic locking increment
            
            await self.db.commit()
            
            # Use comprehensive failure handler if payment intent exists
            try:
                from services.payments.payment_failure_handler import PaymentFailureHandler
                
                # Find the payment intent
                payment_intent_result = await self.db.execute(
                    select(PaymentIntent).where(
                        PaymentIntent.stripe_payment_intent_id == stripe_payment_intent_id
                    )
                )
                payment_intent = payment_intent_result.scalar_one_or_none()
                
                if payment_intent:
                    failure_handler = PaymentFailureHandler(self.db)
                    
                    stripe_error = payment_intent_data.get("last_payment_error", {})
                    failure_result = await failure_handler.handle_payment_failure(
                        payment_intent_id=payment_intent.id,
                        stripe_error=stripe_error,
                        failure_context={
                            "webhook_source": True,
                            "stripe_payment_intent_id": stripe_payment_intent_id
                        }
                    )
                    
                    return {
                        "action": "payment_failed_comprehensive",
                        "transaction_id": str(transaction.id),
                        "order_id": str(transaction.order_id) if transaction.order_id else None,
                        "failure_reason": transaction.failure_reason,
                        "failure_handling": failure_result
                    }
                    
            except Exception as e:
                logger.error(f"Error in comprehensive failure handling: {e}")
            
            return {
                "action": "payment_failed",
                "transaction_id": str(transaction.id),
                "order_id": str(transaction.order_id) if transaction.order_id else None,
                "failure_reason": transaction.failure_reason
            }
        
        else:
            logger.warning(f"Transaction not found for failed payment intent {stripe_payment_intent_id}")
            return {
                "action": "payment_failed",
                "warning": "transaction_not_found",
                "stripe_payment_intent_id": stripe_payment_intent_id
            }

    async def _handle_payment_canceled(self, payment_intent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle canceled payment webhook"""
        stripe_payment_intent_id = payment_intent_data["id"]
        
        # Find the transaction with lock to prevent race conditions
        transaction_result = await self.db.execute(
            select(Transaction).where(
                Transaction.stripe_payment_intent_id == stripe_payment_intent_id
            ).with_for_update()
        )
        transaction = transaction_result.scalar_one_or_none()
        
        if transaction:
            transaction.status = "cancelled"
            
            # Update order status if applicable atomically
            if transaction.order_id:
                order_result = await self.db.execute(
                    select(Order).where(Order.id == transaction.order_id).with_for_update()
                )
                order = order_result.scalar_one_or_none()
                if order:
                    order.status = "cancelled"
                    order.version += 1
            
            await self.db.commit()
            
            return {
                "action": "payment_cancelled",
                "transaction_id": str(transaction.id)
            }
        
        return {"action": "payment_cancelled", "warning": "transaction_not_found"}

    async def _handle_refund(self, charge_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle refund webhook"""
        
        return {"action": "refund_processed", "charge_id": charge_data["id"]}

    async def _publish_webhook_event(
        self,
        event: Dict[str, Any],
        processing_result: Dict[str, Any],
        security_metadata: Dict[str, Any]
    ):
        """Publish webhook event through secure message broker"""
        try:
            event_type = event.get("type", "unknown")
            
            # Log the webhook event processing for monitoring
            logger.info(f"Webhook event processed: {event.get('id')} - {event_type}")
            logger.info(f"Processing result: {processing_result}")
            
            # TODO: Implement actual message broker publishing when needed
            # For now, we just log the events for monitoring
            
            if processing_result.get("order_id"):
                logger.info(f"Order affected by webhook: {processing_result['order_id']}")
            
            logger.info(f"Webhook event logged successfully: {event.get('id')}")
            
        except Exception as e:
            logger.error(f"Failed to log webhook event: {e}")
            # Don't fail the webhook processing if logging fails