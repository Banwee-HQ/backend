# Consolidated payment service with integrated failure handling
# This file includes all payment-related functionality including failure handling

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
from models.payments import PaymentMethod, PaymentIntent, Transaction
from models.orders import Order, OrderItem
from models.subscriptions import Subscription
from models.inventories import Inventory
from models.user import User
from uuid import UUID
from core.utils.uuid_utils import uuid7
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum
from core.config import settings
from core.logging import get_structured_logger
import stripe
import json
import time

# Configure Stripe
stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')

logger = get_structured_logger(__name__)


class PaymentFailureReason(Enum):
    """Payment failure reason categories"""
    INSUFFICIENT_FUNDS = "insufficient_funds"
    CARD_DECLINED = "card_declined"
    EXPIRED_CARD = "expired_card"
    INVALID_CARD = "invalid_card"
    AUTHENTICATION_REQUIRED = "authentication_required"
    PROCESSING_ERROR = "processing_error"
    NETWORK_ERROR = "network_error"
    FRAUD_SUSPECTED = "fraud_suspected"
    LIMIT_EXCEEDED = "limit_exceeded"
    UNKNOWN = "unknown"


class PaymentService:
    """Consolidated payment service with comprehensive payment management"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self._init_failure_handling()

    async def create_payment_method(
        self,
        user_id: UUID,
        stripe_payment_method_id: Optional[str] = None,
        stripe_token: Optional[str] = None,
        payment_method_data: Optional[Dict] = None,
        is_default: bool = False
    ) -> PaymentMethod:
        """Create a new payment method supporting both modern and legacy Stripe APIs"""
        try:
            # Handle modern payment method API
            if stripe_payment_method_id:
                # Get payment method details from Stripe
                stripe_pm = stripe.PaymentMethod.retrieve(stripe_payment_method_id)

                # Ensure user has a Stripe customer and attach payment method
                user_result = await self.db.execute(select(User).where(User.id == user_id))
                user = user_result.scalar_one_or_none()
                if not user:
                    raise HTTPException(status_code=404, detail="User not found")

                if user.stripe_customer_id:
                    try:
                        stripe.Customer.retrieve(user.stripe_customer_id)
                    except stripe.error.InvalidRequestError as retrieve_error:
                        if "No such customer" in str(retrieve_error):
                            customer = stripe.Customer.create(
                                email=getattr(user, "email", None),
                                name=getattr(user, "full_name", None)
                            )
                            user.stripe_customer_id = customer.id
                            await self.db.commit()
                        else:
                            raise
                else:
                    customer = stripe.Customer.create(
                        email=getattr(user, "email", None),
                        name=getattr(user, "full_name", None)
                    )
                    user.stripe_customer_id = customer.id
                    await self.db.commit()

                try:
                    stripe.PaymentMethod.attach(
                        stripe_payment_method_id,
                        customer=user.stripe_customer_id
                    )
                except stripe.error.InvalidRequestError as attach_error:
                    message = str(attach_error).lower()
                    if "already" not in message:
                        raise
                
                # If this is set as default, unset other defaults atomically
                if is_default:
                    # Get existing default payment methods with lock
                    existing_defaults = await self.db.execute(
                        select(PaymentMethod).where(
                            and_(PaymentMethod.user_id == user_id, PaymentMethod.is_default == True)
                        ).with_for_update()
                    )
                    
                    # Update them to not be default
                    for pm in existing_defaults.scalars().all():
                        pm.is_default = False
                
                payment_method = PaymentMethod(
                    user_id=user_id,
                    type=stripe_pm.type,
                    provider="stripe",
                    stripe_payment_method_id=stripe_payment_method_id,
                    is_default=is_default,
                    is_active=True
                )
                
                # Set card-specific details if it's a card
                if stripe_pm.type == "card" and stripe_pm.card:
                    payment_method.last_four = stripe_pm.card.last4
                    payment_method.expiry_month = stripe_pm.card.exp_month
                    payment_method.expiry_year = stripe_pm.card.exp_year
                    payment_method.brand = stripe_pm.card.brand
            
            # Handle legacy token API (deprecated but supported for backward compatibility)
            elif stripe_token:
                # Get token details from Stripe
                stripe_token_obj = stripe.Token.retrieve(stripe_token)
                
                # Create payment method from token (this is the old way)
                stripe_pm = stripe.PaymentMethod.create(
                    type="card",
                    card={"token": stripe_token}
                )

                # Ensure user has a Stripe customer and attach payment method
                user_result = await self.db.execute(select(User).where(User.id == user_id))
                user = user_result.scalar_one_or_none()
                if not user:
                    raise HTTPException(status_code=404, detail="User not found")

                if user.stripe_customer_id:
                    try:
                        stripe.Customer.retrieve(user.stripe_customer_id)
                    except stripe.error.InvalidRequestError as retrieve_error:
                        if "No such customer" in str(retrieve_error):
                            customer = stripe.Customer.create(
                                email=getattr(user, "email", None),
                                name=getattr(user, "full_name", None)
                            )
                            user.stripe_customer_id = customer.id
                            await self.db.commit()
                        else:
                            raise
                else:
                    customer = stripe.Customer.create(
                        email=getattr(user, "email", None),
                        name=getattr(user, "full_name", None)
                    )
                    user.stripe_customer_id = customer.id
                    await self.db.commit()

                try:
                    stripe.PaymentMethod.attach(
                        stripe_pm.id,
                        customer=user.stripe_customer_id
                    )
                except stripe.error.InvalidRequestError as attach_error:
                    message = str(attach_error).lower()
                    if "already" not in message:
                        raise
                
                # If this is set as default, unset other defaults atomically
                if is_default:
                    existing_defaults = await self.db.execute(
                        select(PaymentMethod).where(
                            and_(PaymentMethod.user_id == user_id, PaymentMethod.is_default == True)
                        ).with_for_update()
                    )
                    
                    for pm in existing_defaults.scalars().all():
                        pm.is_default = False
                
                payment_method = PaymentMethod(
                    user_id=user_id,
                    type="card",
                    provider="stripe",
                    stripe_payment_method_id=stripe_pm.id,
                    is_default=is_default,
                    is_active=True
                )
                
                # Set card details from token
                if stripe_token_obj.card:
                    payment_method.last_four = stripe_token_obj.card.last4
                    payment_method.expiry_month = stripe_token_obj.card.exp_month
                    payment_method.expiry_year = stripe_token_obj.card.exp_year
                    payment_method.brand = stripe_token_obj.card.brand
            
            # Handle direct payment method data (from frontend)
            elif payment_method_data:
                # If this is set as default, unset other defaults atomically
                if is_default:
                    existing_defaults = await self.db.execute(
                        select(PaymentMethod).where(
                            and_(PaymentMethod.user_id == user_id, PaymentMethod.is_default == True)
                        ).with_for_update()
                    )
                    
                    for pm in existing_defaults.scalars().all():
                        pm.is_default = False
                
                payment_method = PaymentMethod(
                    user_id=user_id,
                    type=payment_method_data.get("type", "card"),
                    provider=payment_method_data.get("provider", "unknown"),
                    last_four=payment_method_data.get("last_four"),
                    expiry_month=payment_method_data.get("expiry_month"),
                    expiry_year=payment_method_data.get("expiry_year"),
                    brand=payment_method_data.get("provider"),  # Use provider as brand for now
                    is_default=is_default,
                    is_active=True
                )
            
            else:
                raise HTTPException(
                    status_code=400, 
                    detail="Either stripe_payment_method_id, stripe_token, or payment_method_data must be provided"
                )
            
            self.db.add(payment_method)
            await self.db.commit()
            await self.db.refresh(payment_method)
            
            return payment_method
            
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create payment method: {str(e)}")

    async def get_user_payment_methods(self, user_id: UUID) -> List[PaymentMethod]:
        """Get all payment methods for a user"""
        result = await self.db.execute(
            select(PaymentMethod).where(
                and_(PaymentMethod.user_id == user_id, PaymentMethod.is_active == True)
            ).order_by(PaymentMethod.is_default.desc(), PaymentMethod.created_at.desc())
        )
        return result.scalars().all()

    async def delete_payment_method(self, payment_method_id: UUID, user_id: UUID) -> bool:
        """Delete a payment method"""
        result = await self.db.execute(
            select(PaymentMethod).where(
                and_(
                    PaymentMethod.id == payment_method_id,
                    PaymentMethod.user_id == user_id
                )
            )
        )
        payment_method = result.scalar_one_or_none()
        
        if not payment_method:
            raise HTTPException(status_code=404, detail="Payment method not found")
        
        try:
            # Detach from Stripe only if attached to a customer
            if payment_method.stripe_payment_method_id:
                try:
                    stripe_pm = stripe.PaymentMethod.retrieve(payment_method.stripe_payment_method_id)
                    if getattr(stripe_pm, "customer", None):
                        stripe.PaymentMethod.detach(payment_method.stripe_payment_method_id)
                except stripe.error.InvalidRequestError as detach_error:
                    message = str(detach_error).lower()
                    if "not attached" not in message:
                        raise
            
            # Mark as inactive instead of deleting
            payment_method.is_active = False
            await self.db.commit()
            
            return True
            
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")

    async def set_default_payment_method(self, payment_method_id: UUID, user_id: UUID) -> bool:
        """Set a payment method as default for the user"""
        try:
            # Get the payment method to set as default
            result = await self.db.execute(
                select(PaymentMethod).where(
                    and_(
                        PaymentMethod.id == payment_method_id,
                        PaymentMethod.user_id == user_id,
                        PaymentMethod.is_active == True
                    )
                ).with_for_update()
            )
            new_default = result.scalar_one_or_none()
            
            if not new_default:
                return False
            
            # Get all existing default payment methods for this user
            existing_defaults = await self.db.execute(
                select(PaymentMethod).where(
                    and_(
                        PaymentMethod.user_id == user_id,
                        PaymentMethod.is_default == True,
                        PaymentMethod.is_active == True
                    )
                ).with_for_update()
            )
            
            # Unset all existing defaults
            for pm in existing_defaults.scalars().all():
                pm.is_default = False
            
            # Set the new default
            new_default.is_default = True
            
            await self.db.commit()
            return True
            
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to set default payment method: {str(e)}")

    async def update_payment_method(self, payment_method_id: UUID, user_id: UUID, update_data: Dict[str, Any]) -> Optional[PaymentMethod]:
        """Update a payment method"""
        try:
            # Get the payment method
            result = await self.db.execute(
                select(PaymentMethod).where(
                    and_(
                        PaymentMethod.id == payment_method_id,
                        PaymentMethod.user_id == user_id,
                        PaymentMethod.is_active == True
                    )
                ).with_for_update()
            )
            payment_method = result.scalar_one_or_none()
            
            if not payment_method:
                return None
            
            # Update allowed fields
            allowed_fields = ['expiry_month', 'expiry_year']
            for field, value in update_data.items():
                if field in allowed_fields and hasattr(payment_method, field):
                    setattr(payment_method, field, value)
            
            await self.db.commit()
            await self.db.refresh(payment_method)
            return payment_method
            
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to update payment method: {str(e)}")

    async def create_payment_intent(
        self,
        user_id: UUID,
        amount: float,
        currency: str = "USD",
        order_id: Optional[UUID] = None,
        subscription_id: Optional[UUID] = None,
        metadata: Dict[str, Any] = None,
        commit: bool = True
    ) -> PaymentIntent:
        """Create a payment intent with optional transaction control"""
        try:
            # Create Stripe payment intent
            stripe_intent = stripe.PaymentIntent.create(
                amount=int(amount * 100),  # Convert to cents
                currency=currency.lower(),
                automatic_payment_methods={
                    "enabled": True,
                    "allow_redirects": "never"
                },
                metadata=metadata or {},
                idempotency_key=str(uuid7())  # Provide explicit idempotency key
            )
            
            # Create our payment intent record
            payment_intent = PaymentIntent(
                id=uuid7(),
                stripe_payment_intent_id=stripe_intent.id,
                user_id=user_id,
                order_id=order_id,
                subscription_id=subscription_id,
                amount_breakdown={"total": amount, "currency": currency},
                currency=currency,
                status=stripe_intent.status,
                client_secret=stripe_intent.client_secret,
                payment_intent_metadata=metadata
            )
            
            self.db.add(payment_intent)
            if commit:
                await self.db.commit()
                await self.db.refresh(payment_intent)
            
            return payment_intent
            
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")

    async def confirm_payment_intent(
        self,
        payment_intent_id: UUID,
        payment_method_id: str,
        commit: bool = True
    ) -> PaymentIntent:
        """Confirm a payment intent with optional transaction control"""
        result = await self.db.execute(
            select(PaymentIntent).where(PaymentIntent.id == payment_intent_id).with_for_update()
        )
        payment_intent = result.scalar_one_or_none()
        
        if not payment_intent:
            raise HTTPException(status_code=404, detail="Payment intent not found")
        
        try:
            # Confirm with Stripe
            stripe_intent = stripe.PaymentIntent.confirm(
                payment_intent.stripe_payment_intent_id,
                payment_method=payment_method_id
            )
            
            # Update our record atomically
            payment_intent.status = stripe_intent.status
            payment_intent.payment_method_id = payment_method_id
            
            if stripe_intent.status == "succeeded":
                payment_intent.confirmed_at = datetime.utcnow()
                
                # Create transaction record
                transaction = Transaction(
                    user_id=payment_intent.user_id,
                    order_id=payment_intent.order_id,
                    payment_intent_id=payment_intent.id,
                    stripe_payment_intent_id=payment_intent.stripe_payment_intent_id,
                    amount=payment_intent.amount_breakdown.get("total", 0),
                    currency=payment_intent.currency,
                    status="succeeded",
                    transaction_type="payment",
                    description="Payment processed successfully"
                )
                self.db.add(transaction)
                
                # Send secure notification for successful payment (only if committing)
                if commit:
                    await self._send_payment_notification(
                        payment_intent.user_id,
                        payment_intent.order_id,
                        "payment_succeeded",
                        {
                            "payment_intent_id": str(payment_intent.id),
                            "amount": payment_intent.amount_breakdown.get("total", 0),
                            "currency": payment_intent.currency
                        }
                    )
            
            elif stripe_intent.status == "requires_action":
                payment_intent.requires_action = True
                payment_intent.client_secret = stripe_intent.client_secret
            
            if commit:
                await self.db.commit()
                await self.db.refresh(payment_intent)
            
            return payment_intent
            
        except stripe.error.StripeError as e:
            # Use comprehensive failure handler
            from services.payments.payment_failure_handler import PaymentFailureHandler
            
            failure_handler = PaymentFailureHandler(self.db)
            
            # Update payment intent with basic failure info first
            payment_intent.status = "failed"
            payment_intent.failed_at = datetime.utcnow()
            payment_intent.failure_reason = str(e)
            
            if commit:
                await self.db.commit()
                
                # Handle failure comprehensively
                try:
                    stripe_error_details = {
                        "code": getattr(e, 'code', None),
                        "decline_code": getattr(e, 'decline_code', None),
                        "type": getattr(e, 'type', None),
                        "message": str(e),
                        "param": getattr(e, 'param', None)
                    }
                    
                    failure_result = await failure_handler.handle_payment_failure(
                        payment_intent_id=payment_intent.id,
                        stripe_error=stripe_error_details,
                        failure_context={
                            "payment_method_id": payment_method_id,
                            "amount": payment_intent.amount_breakdown.get("total", 0),
                            "currency": payment_intent.currency
                        }
                    )
                    
                    # Send enhanced failure notification
                    await self._send_payment_notification(
                        payment_intent.user_id,
                        payment_intent.order_id,
                        "payment_failed_enhanced",
                        {
                            "payment_intent_id": str(payment_intent.id),
                            "error": str(e),
                            "failure_result": failure_result,
                            "user_message": failure_result.get("user_message"),
                            "next_steps": failure_result.get("next_steps")
                        }
                    )
                    
                except Exception as handler_error:
                    logger.error(f"Error in failure handler: {handler_error}")
                    # Fall back to basic notification
                    await self._send_payment_notification(
                        payment_intent.user_id,
                        payment_intent.order_id,
                        "payment_failed",
                        {
                            "payment_intent_id": str(payment_intent.id),
                            "error": str(e)
                        }
                    )
            
            raise HTTPException(status_code=400, detail=f"Payment failed: {str(e)}")

    async def process_payment_with_timeout_and_retry(
        self,
        user_id: UUID,
        amount: float,
        payment_method_id: UUID,
        order_id: Optional[UUID] = None,
        subscription_id: Optional[UUID] = None,
        timeout_seconds: int = 45,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Process payment with timeout, retry logic, and comprehensive error handling
        """
        import asyncio
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Payment attempt {attempt + 1}/{max_retries} for user {user_id}, amount {amount}")
                
                # Wrap payment processing with timeout
                payment_task = self._process_payment_internal(
                    user_id, amount, payment_method_id, order_id, subscription_id, commit=False
                )
                
                payment_result = await asyncio.wait_for(payment_task, timeout=timeout_seconds)
                
                # If successful, commit the transaction
                await self.db.commit()
                
                logger.info(f"Payment successful on attempt {attempt + 1} for user {user_id}")
                return payment_result
                
            except asyncio.TimeoutError:
                logger.error(f"Payment timeout on attempt {attempt + 1} after {timeout_seconds}s for user {user_id}")
                await self.db.rollback()
                
                if attempt == max_retries - 1:
                    # Final attempt failed
                    raise HTTPException(
                        status_code=408, 
                        detail=f"Payment processing timed out after {max_retries} attempts. Please try again."
                    )
                
                # Wait before retry (exponential backoff)
                wait_time = 2 ** attempt
                logger.info(f"Retrying payment in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
                
            except stripe.error.RateLimitError as e:
                logger.error(f"Stripe rate limit on attempt {attempt + 1}: {e}")
                await self.db.rollback()
                
                if attempt == max_retries - 1:
                    raise HTTPException(status_code=429, detail="Payment service temporarily unavailable. Please try again later.")
                
                # Wait longer for rate limit
                await asyncio.sleep(5 * (attempt + 1))
                
            except stripe.error.CardError as e:
                # Card errors are not retryable
                logger.error(f"Card error for user {user_id}: {e}")
                await self.db.rollback()
                
                # Record payment failure
                await self._record_payment_failure(
                    user_id=user_id,
                    order_id=order_id,
                    error_code=e.code,
                    error_message=str(e),
                    failure_reason=self._categorize_stripe_error(e)
                )
                
                raise HTTPException(
                    status_code=400, 
                    detail=f"Payment failed: {e.user_message or str(e)}"
                )
                
            except Exception as e:
                logger.error(f"Payment error on attempt {attempt + 1} for user {user_id}: {e}")
                await self.db.rollback()
                
                if attempt == max_retries - 1:
                    raise HTTPException(
                        status_code=500, 
                        detail=f"Payment processing failed after {max_retries} attempts: {str(e)}"
                    )
                
                # Wait before retry
                await asyncio.sleep(2 ** attempt)
        
        # Should never reach here
        raise HTTPException(status_code=500, detail="Payment processing failed unexpectedly")

    async def _process_payment_internal(
        self,
        user_id: UUID,
        amount: float,
        payment_method_id: UUID,
        order_id: Optional[UUID] = None,
        subscription_id: Optional[UUID] = None,
        commit: bool = True
    ) -> Dict[str, Any]:
        """Internal payment processing method"""
        try:
            # Get payment method with expiry validation
            result = await self.db.execute(
                select(PaymentMethod).where(
                    and_(
                        PaymentMethod.id == payment_method_id,
                        PaymentMethod.user_id == user_id,
                        PaymentMethod.is_active == True
                    )
                )
            )
            payment_method = result.scalar_one_or_none()
            
            if not payment_method:
                raise HTTPException(status_code=404, detail="Payment method not found")
            
            # Validate payment method expiry
            if payment_method.expires_at and payment_method.expires_at < datetime.utcnow():
                raise HTTPException(
                    status_code=400, 
                    detail="Payment method has expired. Please update your payment information."
                )
            
            # Create and confirm payment intent
            payment_intent = await self.create_payment_intent(
                user_id=user_id,
                amount=amount,
                order_id=order_id,
                subscription_id=subscription_id,
                commit=commit
            )
            
            confirmed_intent = await self.confirm_payment_intent(
                payment_intent.id,
                payment_method.stripe_payment_method_id,
                commit=commit
            )
            
            return {
                "status": confirmed_intent.status,
                "payment_intent_id": str(confirmed_intent.id),
                "requires_action": confirmed_intent.requires_action,
                "client_secret": confirmed_intent.client_secret
            }
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Payment processing failed: {str(e)}")

    async def process_payment_idempotent(
        self,
        user_id: UUID,
        order_id: UUID,
        amount: float,
        payment_method_id: UUID,
        idempotency_key: str,
        request_id: Optional[str] = None,
        frontend_calculated_amount: Optional[float] = None  # Amount calculated by frontend
    ) -> Dict[str, Any]:
        """
        Process payment with idempotency guarantee and price validation
        Validates that frontend-calculated prices match backend calculations
        """
        start_time = time.time()
        
        if not request_id:
            request_id = str(uuid7())
        
        try:
            # Validate frontend price against backend calculation
            if frontend_calculated_amount is not None:
                price_difference = abs(amount - frontend_calculated_amount)
                if price_difference > 0.01:  # Allow 1 cent tolerance for rounding
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Price mismatch: frontend calculated {frontend_calculated_amount}, backend calculated {amount}"
                    )
            
            # Check for existing transaction with idempotency key
            existing_result = await self.db.execute(
                select(Transaction).where(
                    Transaction.idempotency_key == idempotency_key
                )
            )
            existing_transaction = existing_result.scalar_one_or_none()
            
            if existing_transaction:
                logger.info(f"Returning cached payment result for {idempotency_key}")
                return {
                    "status": existing_transaction.status,
                    "transaction_id": str(existing_transaction.id),
                    "cached": True,
                    "amount": existing_transaction.amount
                }
            
            # Get payment method with validation
            pm_result = await self.db.execute(
                select(PaymentMethod).where(
                    and_(
                        PaymentMethod.id == payment_method_id,
                        PaymentMethod.user_id == user_id,
                        PaymentMethod.is_active == True
                    )
                )
            )
            payment_method = pm_result.scalar_one_or_none()
            
            if not payment_method:
                raise HTTPException(status_code=404, detail="Payment method not found")

            # Ensure user has a Stripe customer and attach payment method
            user_result = await self.db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            if user.stripe_customer_id:
                try:
                    stripe.Customer.retrieve(user.stripe_customer_id)
                except stripe.error.InvalidRequestError as retrieve_error:
                    if "No such customer" in str(retrieve_error):
                        customer = stripe.Customer.create(
                            email=getattr(user, "email", None),
                            name=getattr(user, "full_name", None)
                        )
                        user.stripe_customer_id = customer.id
                        await self.db.commit()
                    else:
                        raise
            else:
                customer = stripe.Customer.create(
                    email=getattr(user, "email", None),
                    name=getattr(user, "full_name", None)
                )
                user.stripe_customer_id = customer.id
                await self.db.commit()

            # Attach payment method to customer if needed
            try:
                stripe.PaymentMethod.attach(
                    payment_method.stripe_payment_method_id,
                    customer=user.stripe_customer_id
                )
            except stripe.error.InvalidRequestError as attach_error:
                # If already attached, Stripe returns an error; safe to ignore
                message = str(attach_error).lower()
                if "no such customer" in message:
                    customer = stripe.Customer.create(
                        email=getattr(user, "email", None),
                        name=getattr(user, "full_name", None)
                    )
                    user.stripe_customer_id = customer.id
                    await self.db.commit()
                    stripe.PaymentMethod.attach(
                        payment_method.stripe_payment_method_id,
                        customer=user.stripe_customer_id
                    )
                elif "already" not in message:
                    raise
            
            # Create Stripe payment intent with idempotency key
            stripe_intent = stripe.PaymentIntent.create(
                amount=int(amount * 100),  # Convert to cents
                currency="USD",
                idempotency_key=idempotency_key,  # Stripe-level deduplication
                customer=user.stripe_customer_id,
                automatic_payment_methods={
                    "enabled": True,
                    "allow_redirects": "never"
                },
                metadata={
                    "order_id": str(order_id),
                    "user_id": str(user_id),
                    "request_id": request_id
                }
            )

            # Create PaymentIntent record for admin visibility
            payment_intent_record = PaymentIntent(
                id=uuid7(),
                stripe_payment_intent_id=stripe_intent.id,
                user_id=user_id,
                order_id=order_id,
                amount_breakdown={"total": amount, "currency": "USD"},
                currency="USD",
                status=stripe_intent.status,
                payment_method_id=payment_method.stripe_payment_method_id,
                payment_method_type=payment_method.type,
                requires_action=stripe_intent.status == "requires_action",
                client_secret=stripe_intent.client_secret,
                payment_intent_metadata={
                    "request_id": request_id,
                    "idempotency_key": idempotency_key
                }
            )
            self.db.add(payment_intent_record)
            
            # Confirm payment
            try:
                confirmed = stripe.PaymentIntent.confirm(
                    stripe_intent.id,
                    payment_method=payment_method.stripe_payment_method_id,
                    idempotency_key=f"{idempotency_key}:confirm"  # Separate idempotency for confirm
                )
            except stripe.error.StripeError as e:
                message = str(e).lower()
                if "previously used" in message and "may not be used again" in message:
                    payment_method.is_active = False
                    await self.db.commit()
                    raise HTTPException(
                        status_code=400,
                        detail="Payment method is no longer usable. Please add a new card and try again."
                    )
                raise
            
            # Create transaction record with idempotency key
            transaction = Transaction(
                user_id=user_id,
                order_id=order_id,
                payment_intent_id=None,
                stripe_payment_intent_id=stripe_intent.id,
                amount=amount,
                currency="USD",
                status=confirmed.status,
                transaction_type="payment",
                idempotency_key=idempotency_key,  # Store for deduplication
                request_id=request_id,
                transaction_metadata=json.dumps({
                    "stripe_request_id": getattr(confirmed, 'request_id', None),
                    "timestamp": datetime.utcnow().isoformat(),
                    "payment_method_type": str(payment_method.type),
                    "frontend_amount": frontend_calculated_amount,
                    "price_validated": frontend_calculated_amount is not None
                })
            )

            # Update PaymentIntent record status
            payment_intent_record.status = confirmed.status
            payment_intent_record.confirmed_at = datetime.utcnow() if confirmed.status == "succeeded" else None
            if confirmed.status == "requires_action":
                payment_intent_record.requires_action = True
            
            self.db.add(transaction)
            await self.db.commit()
            await self.db.refresh(transaction)
            
            return {
                "status": confirmed.status,
                "transaction_id": str(transaction.id),
                "cached": False,
                "amount": amount,
                "processing_time_ms": (time.time() - start_time) * 1000
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error for idempotency key {idempotency_key}: {e}")
            raise HTTPException(status_code=400, detail=f"Payment failed: {str(e)}")
        
        except Exception as e:
            logger.error(f"Payment processing error for idempotency key {idempotency_key}: {e}")
            raise HTTPException(status_code=500, detail=f"Payment processing failed: {str(e)}")

    async def validate_order_pricing(
        self,
        order_items: List[Dict[str, Any]],
        shipping_cost: float = 0.0,
        tax_amount: float = 0.0,
        discount_amount: float = 0.0
    ) -> Dict[str, Any]:
        """
        Validate order pricing by recalculating from backend data
        Never trust frontend prices - always validate against backend
        """
        from models.product import ProductVariant
        
        total_items_cost = 0.0
        validated_items = []
        
        for item in order_items:
            variant_id = UUID(item["variant_id"])
            quantity = int(item["quantity"])
            frontend_price = float(item.get("price_per_unit", 0))
            
            # Get actual price from database
            variant_result = await self.db.execute(
                select(ProductVariant).where(ProductVariant.id == variant_id)
            )
            variant = variant_result.scalar_one_or_none()
            
            if not variant:
                raise HTTPException(status_code=404, detail=f"Product variant {variant_id} not found")
            
            backend_price = float(variant.price)
            
            # Validate price matches (allow small rounding differences)
            if abs(frontend_price - backend_price) > 0.01:
                raise HTTPException(
                    status_code=400,
                    detail=f"Price mismatch for variant {variant_id}: frontend {frontend_price}, backend {backend_price}"
                )
            
            item_total = backend_price * quantity
            total_items_cost += item_total
            
            validated_items.append({
                "variant_id": str(variant_id),
                "quantity": quantity,
                "price_per_unit": backend_price,
                "total_price": item_total,
                "variant_name": variant.name
            })
        
        # Calculate final total
        subtotal = total_items_cost
        total_after_discount = subtotal - discount_amount
        total_with_tax = total_after_discount + tax_amount
        final_total = total_with_tax + shipping_cost
        
        return {
            "items": validated_items,
            "subtotal": subtotal,
            "discount_amount": discount_amount,
            "tax_amount": tax_amount,
            "shipping_cost": shipping_cost,
            "final_total": final_total,
            "validation_passed": True
        }

    async def get_user_transactions(
        self,
        user_id: UUID,
        page: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        """Get user transaction history"""
        offset = (page - 1) * limit
        
        query = select(Transaction).where(Transaction.user_id == user_id).order_by(
            Transaction.created_at.desc()
        ).offset(offset).limit(limit)
        
        result = await self.db.execute(query)
        transactions = result.scalars().all()
        
        # Get total count
        count_result = await self.db.execute(
            select(Transaction).where(Transaction.user_id == user_id)
        )
        total = len(count_result.scalars().all())
        
        return {
            "transactions": [transaction.to_dict() for transaction in transactions],
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }

    async def create_refund(
        self,
        payment_intent_id: UUID,
        amount: Optional[float] = None,
        reason: str = "requested_by_customer"
    ) -> Transaction:
        """Create a refund for a payment"""
        result = await self.db.execute(
            select(PaymentIntent).where(PaymentIntent.id == payment_intent_id)
        )
        payment_intent = result.scalar_one_or_none()
        
        if not payment_intent:
            raise HTTPException(status_code=404, detail="Payment intent not found")
        
        if payment_intent.status != "succeeded":
            raise HTTPException(status_code=400, detail="Cannot refund unsuccessful payment")
        
        try:
            # Create refund in Stripe
            refund_amount = amount or payment_intent.amount_breakdown.get("total", 0)
            stripe_refund = stripe.Refund.create(
                payment_intent=payment_intent.stripe_payment_intent_id,
                amount=int(refund_amount * 100),  # Convert to cents
                reason=reason
            )
            
            # Create transaction record
            transaction = Transaction(
                user_id=payment_intent.user_id,
                order_id=payment_intent.order_id,
                payment_intent_id=payment_intent.id,
                stripe_payment_intent_id=payment_intent.stripe_payment_intent_id,
                amount=-refund_amount,  # Negative for refund
                currency=payment_intent.currency,
                status="succeeded",
                transaction_type="refund",
                description=f"Refund processed: {reason}",
                transaction_metadata={"stripe_refund_id": stripe_refund.id}
            )
            
            self.db.add(transaction)
            await self.db.commit()
            await self.db.refresh(transaction)
            
            return transaction
            
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Refund failed: {str(e)}")
    
    async def _send_payment_notification(
        self,
        user_id: UUID,
        order_id: Optional[UUID],
        event_type: str,
        data: Dict[str, Any]
    ):
        """Send payment notification via secure message broker"""
        try:
            # Publish payment event
            await publish_payment_event(
                event_type=event_type,
                payment_data={
                    "user_id": str(user_id),
                    "order_id": str(order_id) if order_id else None,
                    "event_data": data,
                    "timestamp": datetime.utcnow().isoformat()
                },
                correlation_id=str(order_id) if order_id else str(user_id)
            )
            
            # Publish notification for real-time updates
            await publish_notification({
                "type": "payment_update",
                "user_id": str(user_id),
                "order_id": str(order_id) if order_id else None,
                "event_type": event_type,
                "data": data,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            logger.info(f"Payment notification sent securely: {event_type} for user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to send payment notification: {e}")
            # Don't fail payment processing if notification fails
    # ============================================================================
    # PAYMENT FAILURE HANDLING METHODS
    # ============================================================================
    
    def _init_failure_handling(self):
        """Initialize failure handling components"""
        # Failure reason mapping from Stripe error codes
        self.stripe_error_mapping = {
            "insufficient_funds": PaymentFailureReason.INSUFFICIENT_FUNDS,
            "card_declined": PaymentFailureReason.CARD_DECLINED,
            "expired_card": PaymentFailureReason.EXPIRED_CARD,
            "incorrect_number": PaymentFailureReason.INVALID_CARD,
            "incorrect_cvc": PaymentFailureReason.INVALID_CARD,
            "authentication_required": PaymentFailureReason.AUTHENTICATION_REQUIRED,
            "processing_error": PaymentFailureReason.PROCESSING_ERROR,
            "rate_limit": PaymentFailureReason.LIMIT_EXCEEDED,
            "fraud": PaymentFailureReason.FRAUD_SUSPECTED,
        }

    async def handle_payment_failure(
        self,
        payment_intent_id: UUID,
        stripe_error: Optional[Dict] = None,
        failure_context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive payment failure handling with recovery mechanisms
        
        Args:
            payment_intent_id: Failed payment intent ID
            stripe_error: Stripe error details
            failure_context: Additional failure context
            
        Returns:
            Recovery action details
        """
        try:
            # Get payment intent with lock
            payment_intent = await self._get_payment_intent_with_lock(payment_intent_id)
            
            if not payment_intent:
                raise HTTPException(
                    status_code=404,
                    detail=f"Payment intent {payment_intent_id} not found"
                )
            
            # Categorize failure reason
            failure_reason = self._categorize_failure_reason(stripe_error)
            
            # Update payment intent with failure details
            await self._update_payment_intent_failure(payment_intent, stripe_error, failure_reason)
            
            # Handle order-specific failures
            recovery_actions = []
            if payment_intent.order_id:
                order_actions = await self._handle_order_payment_failure(
                    payment_intent.order_id, 
                    failure_reason,
                    failure_context
                )
                recovery_actions.extend(order_actions)
            
            # Handle subscription-specific failures
            if payment_intent.subscription_id:
                subscription_actions = await self._handle_subscription_payment_failure(
                    payment_intent.subscription_id,
                    failure_reason,
                    failure_context
                )
                recovery_actions.extend(subscription_actions)
            
            # Send user notification
            await self._send_failure_notification(payment_intent, failure_reason)
            
            # Determine retry strategy
            retry_strategy = self._determine_retry_strategy(failure_reason, payment_intent)
            
            await self.db.commit()
            
            logger.info(f"Payment failure handled: {payment_intent_id}, reason: {failure_reason.value}")
            
            return {
                "payment_intent_id": str(payment_intent_id),
                "failure_reason": failure_reason.value,
                "recovery_actions": recovery_actions,
                "retry_strategy": retry_strategy,
                "user_message": self._get_user_friendly_message(failure_reason),
                "next_steps": self._get_next_steps(failure_reason)
            }
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error handling payment failure for {payment_intent_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to handle payment failure: {str(e)}"
            )

    async def _get_payment_intent_with_lock(self, payment_intent_id: UUID) -> Optional[PaymentIntent]:
        """Get payment intent with SELECT ... FOR UPDATE lock"""
        result = await self.db.execute(
            select(PaymentIntent)
            .where(PaymentIntent.id == payment_intent_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    def _categorize_failure_reason(self, stripe_error: Optional[Dict]) -> PaymentFailureReason:
        """Categorize payment failure reason from Stripe error"""
        if not stripe_error:
            return PaymentFailureReason.UNKNOWN
        
        error_code = stripe_error.get("code", "").lower()
        decline_code = stripe_error.get("decline_code", "").lower()
        
        # Check error code first
        if error_code in self.stripe_error_mapping:
            return self.stripe_error_mapping[error_code]
        
        # Check decline code
        if decline_code in self.stripe_error_mapping:
            return self.stripe_error_mapping[decline_code]
        
        # Check error type
        error_type = stripe_error.get("type", "").lower()
        if "card" in error_type:
            return PaymentFailureReason.CARD_DECLINED
        elif "authentication" in error_type:
            return PaymentFailureReason.AUTHENTICATION_REQUIRED
        
        return PaymentFailureReason.UNKNOWN

    async def _update_payment_intent_failure(
        self,
        payment_intent: PaymentIntent,
        stripe_error: Optional[Dict],
        failure_reason: PaymentFailureReason
    ):
        """Update payment intent with failure details"""
        payment_intent.status = "failed"
        payment_intent.failed_at = datetime.utcnow()
        payment_intent.failure_reason = failure_reason.value
        
        # Store detailed error information
        if stripe_error:
            payment_intent.failure_metadata = {
                "stripe_error": stripe_error,
                "categorized_reason": failure_reason.value,
                "failed_at": datetime.utcnow().isoformat(),
                "retry_count": payment_intent.failure_metadata.get("retry_count", 0) + 1 if payment_intent.failure_metadata else 1
            }

    async def _handle_order_payment_failure(
        self,
        order_id: UUID,
        failure_reason: PaymentFailureReason,
        failure_context: Optional[Dict]
    ) -> List[Dict[str, Any]]:
        """Handle payment failure for orders with inventory restoration"""
        recovery_actions = []
        
        try:
            # Get order with lock
            order_result = await self.db.execute(
                select(Order)
                .where(Order.id == order_id)
                .options(selectinload(Order.items).selectinload(OrderItem.variant))
                .with_for_update()
            )
            order = order_result.scalar_one_or_none()
            
            if not order:
                return recovery_actions
            
            # Update order status
            order.status = "payment_failed"
            order.version += 1
            
            # Store failure details in order metadata
            if not order.order_metadata:
                order.order_metadata = {}
            
            order.order_metadata.update({
                "payment_failure": {
                    "reason": failure_reason.value,
                    "failed_at": datetime.utcnow().isoformat(),
                    "context": failure_context or {}
                }
            })
            
            # Restore inventory for failed payment
            from services.inventory import InventoryService
            inventory_service = InventoryService(self.db)
            inventory_restored = []
            
            for item in order.items:
                if item.variant:
                    try:
                        # Restore stock atomically
                        restore_result = await inventory_service.increment_stock_on_cancellation(
                            variant_id=item.variant_id,
                            quantity=item.quantity,
                            location_id=item.variant.inventory.location_id if item.variant.inventory else None,
                            order_id=order_id,
                            user_id=order.user_id
                        )
                        
                        inventory_restored.append({
                            "variant_id": str(item.variant_id),
                            "quantity_restored": item.quantity,
                            "product_name": item.variant.product.name if item.variant.product else "Unknown"
                        })
                        
                    except Exception as e:
                        logger.error(f"Failed to restore inventory for variant {item.variant_id}: {e}")
            
            if inventory_restored:
                recovery_actions.append({
                    "action": "inventory_restored",
                    "details": inventory_restored
                })
            
            # Set order expiry for retry window
            retry_window_hours = self._get_retry_window_hours(failure_reason)
            order.order_metadata["payment_retry_expires_at"] = (
                datetime.utcnow() + timedelta(hours=retry_window_hours)
            ).isoformat()
            
            recovery_actions.append({
                "action": "order_marked_for_retry",
                "retry_expires_at": order.order_metadata["payment_retry_expires_at"],
                "retry_window_hours": retry_window_hours
            })
            
        except Exception as e:
            logger.error(f"Error handling order payment failure {order_id}: {e}")
            recovery_actions.append({
                "action": "error",
                "message": f"Failed to handle order payment failure: {str(e)}"
            })
        
        return recovery_actions

    async def _handle_subscription_payment_failure(
        self,
        subscription_id: UUID,
        failure_reason: PaymentFailureReason,
        failure_context: Optional[Dict]
    ) -> List[Dict[str, Any]]:
        """Handle payment failure for subscriptions with grace period"""
        recovery_actions = []
        
        try:
            # Get subscription with lock
            subscription_result = await self.db.execute(
                select(Subscription)
                .where(Subscription.id == subscription_id)
                .with_for_update()
            )
            subscription = subscription_result.scalar_one_or_none()
            
            if not subscription:
                return recovery_actions
            
            # Determine grace period based on failure reason
            grace_period_days = self._get_subscription_grace_period(failure_reason)
            
            # Update subscription status and metadata
            if failure_reason in [PaymentFailureReason.INSUFFICIENT_FUNDS, PaymentFailureReason.CARD_DECLINED]:
                subscription.status = "payment_failed"
                subscription.grace_period_ends_at = datetime.utcnow() + timedelta(days=grace_period_days)
            else:
                subscription.status = "suspended"
            
            # Store failure details
            if not subscription.subscription_metadata:
                subscription.subscription_metadata = {}
            
            subscription.subscription_metadata.update({
                "payment_failure": {
                    "reason": failure_reason.value,
                    "failed_at": datetime.utcnow().isoformat(),
                    "grace_period_days": grace_period_days,
                    "retry_count": subscription.subscription_metadata.get("payment_failure", {}).get("retry_count", 0) + 1
                }
            })
            
            recovery_actions.extend([
                {
                    "action": "subscription_grace_period_activated",
                    "grace_period_days": grace_period_days,
                    "grace_period_ends_at": subscription.grace_period_ends_at.isoformat() if subscription.grace_period_ends_at else None
                }
            ])
            
        except Exception as e:
            logger.error(f"Error handling subscription payment failure {subscription_id}: {e}")
            recovery_actions.append({
                "action": "error",
                "message": f"Failed to handle subscription payment failure: {str(e)}"
            })
        
        return recovery_actions

    async def _send_failure_notification(
        self,
        payment_intent: PaymentIntent,
        failure_reason: PaymentFailureReason
    ):
        """Send user-friendly notification about payment failure"""
        try:
            user_message = self._get_user_friendly_message(failure_reason)
            notification_type = "error" if failure_reason in [
                PaymentFailureReason.FRAUD_SUSPECTED,
                PaymentFailureReason.PROCESSING_ERROR
            ] else "warning"
            
            # For payment failures, we could send an email notification instead
            # For now, we'll just log the failure
            logger.info(f"Payment failure notification would be sent to user {payment_intent.user_id}: {user_message}")
            
        except Exception as e:
            logger.error(f"Error handling payment failure notification: {e}")

    def _determine_retry_strategy(
        self,
        failure_reason: PaymentFailureReason,
        payment_intent: PaymentIntent
    ) -> Dict[str, Any]:
        """Determine appropriate retry strategy based on failure reason"""
        retry_count = payment_intent.failure_metadata.get("retry_count", 0) if payment_intent.failure_metadata else 0
        
        # No retry for certain failure types
        if failure_reason in [
            PaymentFailureReason.FRAUD_SUSPECTED,
            PaymentFailureReason.INVALID_CARD,
            PaymentFailureReason.EXPIRED_CARD
        ]:
            return {
                "should_retry": False,
                "reason": "failure_type_not_retryable",
                "max_retries_reached": False
            }
        
        # Check max retries
        max_retries = 3
        if retry_count >= max_retries:
            return {
                "should_retry": False,
                "reason": "max_retries_reached",
                "max_retries_reached": True,
                "retry_count": retry_count
            }
        
        # Determine retry delay based on failure reason
        retry_delays = {
            PaymentFailureReason.INSUFFICIENT_FUNDS: [24, 72, 168],  # 1 day, 3 days, 1 week
            PaymentFailureReason.CARD_DECLINED: [1, 6, 24],  # 1 hour, 6 hours, 1 day
            PaymentFailureReason.PROCESSING_ERROR: [0.5, 2, 6],  # 30 min, 2 hours, 6 hours
            PaymentFailureReason.NETWORK_ERROR: [0.25, 1, 4],  # 15 min, 1 hour, 4 hours
            PaymentFailureReason.AUTHENTICATION_REQUIRED: [0, 0, 0],  # Immediate retry allowed
        }
        
        delay_hours = retry_delays.get(failure_reason, [1, 6, 24])
        next_retry_delay = delay_hours[min(retry_count, len(delay_hours) - 1)]
        
        return {
            "should_retry": True,
            "retry_count": retry_count,
            "max_retries": max_retries,
            "next_retry_in_hours": next_retry_delay,
            "next_retry_at": (datetime.utcnow() + timedelta(hours=next_retry_delay)).isoformat(),
            "retry_method": "automatic" if failure_reason in [
                PaymentFailureReason.PROCESSING_ERROR,
                PaymentFailureReason.NETWORK_ERROR
            ] else "manual"
        }

    def _get_retry_window_hours(self, failure_reason: PaymentFailureReason) -> int:
        """Get retry window in hours for order payment failures"""
        retry_windows = {
            PaymentFailureReason.INSUFFICIENT_FUNDS: 168,  # 1 week
            PaymentFailureReason.CARD_DECLINED: 72,  # 3 days
            PaymentFailureReason.PROCESSING_ERROR: 24,  # 1 day
            PaymentFailureReason.NETWORK_ERROR: 12,  # 12 hours
            PaymentFailureReason.AUTHENTICATION_REQUIRED: 48,  # 2 days
        }
        return retry_windows.get(failure_reason, 48)  # Default 2 days

    def _get_subscription_grace_period(self, failure_reason: PaymentFailureReason) -> int:
        """Get grace period in days for subscription payment failures"""
        grace_periods = {
            PaymentFailureReason.INSUFFICIENT_FUNDS: 7,  # 1 week
            PaymentFailureReason.CARD_DECLINED: 5,  # 5 days
            PaymentFailureReason.PROCESSING_ERROR: 3,  # 3 days
            PaymentFailureReason.NETWORK_ERROR: 1,  # 1 day
            PaymentFailureReason.AUTHENTICATION_REQUIRED: 3,  # 3 days
        }
        return grace_periods.get(failure_reason, 3)  # Default 3 days

    def _get_user_friendly_message(self, failure_reason: PaymentFailureReason) -> str:
        """Get user-friendly message for payment failure"""
        messages = {
            PaymentFailureReason.INSUFFICIENT_FUNDS: "Your payment was declined due to insufficient funds. Please check your account balance and try again.",
            PaymentFailureReason.CARD_DECLINED: "Your card was declined. Please try a different payment method or contact your bank.",
            PaymentFailureReason.EXPIRED_CARD: "Your card has expired. Please update your payment method with a valid card.",
            PaymentFailureReason.INVALID_CARD: "There's an issue with your card details. Please check and update your payment information.",
            PaymentFailureReason.AUTHENTICATION_REQUIRED: "Additional authentication is required for this payment. Please complete the verification process.",
            PaymentFailureReason.PROCESSING_ERROR: "We encountered a temporary issue processing your payment. We'll retry automatically.",
            PaymentFailureReason.NETWORK_ERROR: "There was a network issue during payment processing. We'll retry automatically.",
            PaymentFailureReason.FRAUD_SUSPECTED: "This payment was flagged for security reasons. Please contact support for assistance.",
            PaymentFailureReason.LIMIT_EXCEEDED: "This payment exceeds your card's limit. Please try a smaller amount or different payment method.",
            PaymentFailureReason.UNKNOWN: "We encountered an issue processing your payment. Please try again or contact support."
        }
        return messages.get(failure_reason, messages[PaymentFailureReason.UNKNOWN])

    def _get_next_steps(self, failure_reason: PaymentFailureReason) -> List[str]:
        """Get recommended next steps for user"""
        steps = {
            PaymentFailureReason.INSUFFICIENT_FUNDS: [
                "Check your account balance",
                "Add funds to your account",
                "Try again once funds are available"
            ],
            PaymentFailureReason.CARD_DECLINED: [
                "Contact your bank to authorize the payment",
                "Try a different payment method",
                "Check if your card is blocked for online purchases"
            ],
            PaymentFailureReason.EXPIRED_CARD: [
                "Update your payment method",
                "Add a new valid card",
                "Remove the expired card"
            ],
            PaymentFailureReason.INVALID_CARD: [
                "Check your card number and details",
                "Update your payment information",
                "Try a different card"
            ],
            PaymentFailureReason.AUTHENTICATION_REQUIRED: [
                "Complete the authentication process",
                "Check for SMS or email verification",
                "Contact your bank if needed"
            ],
            PaymentFailureReason.PROCESSING_ERROR: [
                "Wait for automatic retry",
                "Try again in a few minutes",
                "Contact support if issue persists"
            ],
            PaymentFailureReason.FRAUD_SUSPECTED: [
                "Contact our support team",
                "Verify your identity",
                "Use a different payment method"
            ],
            PaymentFailureReason.LIMIT_EXCEEDED: [
                "Contact your bank to increase limits",
                "Try a smaller amount",
                "Use a different payment method"
            ]
        }
        return steps.get(failure_reason, [
            "Try again with a different payment method",
            "Contact support for assistance"
        ])

    async def retry_failed_payment(
        self,
        payment_intent_id: UUID,
        new_payment_method_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Retry a failed payment with optional new payment method"""
        try:
            # Get payment intent with lock
            payment_intent = await self._get_payment_intent_with_lock(payment_intent_id)
            
            if not payment_intent:
                raise HTTPException(
                    status_code=404,
                    detail="Payment intent not found"
                )
            
            if payment_intent.status != "failed":
                raise HTTPException(
                    status_code=400,
                    detail="Can only retry failed payments"
                )
            
            # Check if retry is allowed
            failure_reason = PaymentFailureReason(payment_intent.failure_reason) if payment_intent.failure_reason else PaymentFailureReason.UNKNOWN
            retry_strategy = self._determine_retry_strategy(failure_reason, payment_intent)
            
            if not retry_strategy["should_retry"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Payment retry not allowed: {retry_strategy['reason']}"
                )
            
            # Update payment method if provided
            if new_payment_method_id:
                payment_intent.payment_method_id = new_payment_method_id
            
            # Reset payment intent for retry
            payment_intent.status = "requires_payment_method"
            payment_intent.failed_at = None
            payment_intent.failure_reason = None
            
            # Update retry count
            if not payment_intent.failure_metadata:
                payment_intent.failure_metadata = {}
            payment_intent.failure_metadata["retry_count"] = payment_intent.failure_metadata.get("retry_count", 0) + 1
            payment_intent.failure_metadata["last_retry_at"] = datetime.utcnow().isoformat()
            
            await self.db.commit()
            
            return {
                "payment_intent_id": str(payment_intent_id),
                "status": "ready_for_retry",
                "retry_count": payment_intent.failure_metadata["retry_count"]
            }
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error retrying payment {payment_intent_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retry payment: {str(e)}"
            )

    async def get_payment_failure_status(
        self,
        payment_intent_id: UUID,
        user_id: UUID
    ) -> Dict[str, Any]:
        """Get detailed status of a failed payment"""
        try:
            # Get payment intent
            result = await self.db.execute(
                select(PaymentIntent).where(
                    PaymentIntent.id == payment_intent_id,
                    PaymentIntent.user_id == user_id
                )
            )
            payment_intent = result.scalar_one_or_none()
            
            if not payment_intent:
                raise HTTPException(
                    status_code=404,
                    detail="Payment intent not found"
                )
            
            if payment_intent.status != "failed":
                return {
                    "payment_intent_id": str(payment_intent_id),
                    "status": payment_intent.status,
                    "is_failed": False
                }
            
            # Get retry strategy
            failure_reason = PaymentFailureReason(payment_intent.failure_reason) if payment_intent.failure_reason else PaymentFailureReason.UNKNOWN
            retry_strategy = self._determine_retry_strategy(failure_reason, payment_intent)
            
            return {
                "payment_intent_id": str(payment_intent_id),
                "status": payment_intent.status,
                "is_failed": True,
                "failure_reason": payment_intent.failure_reason,
                "failed_at": payment_intent.failed_at.isoformat() if payment_intent.failed_at else None,
                "failure_metadata": payment_intent.failure_metadata or {},
                "retry_strategy": retry_strategy,
                "user_message": self._get_user_friendly_message(failure_reason),
                "next_steps": self._get_next_steps(failure_reason),
                "order_id": str(payment_intent.order_id) if payment_intent.order_id else None,
                "subscription_id": str(payment_intent.subscription_id) if payment_intent.subscription_id else None,
                "amount": payment_intent.amount_breakdown.get("total", 0) if payment_intent.amount_breakdown else 0,
                "currency": payment_intent.currency
            }
            
        except Exception as e:
            logger.error(f"Error getting payment failure status: {e}")
            raise HTTPException(
                status_code=500,
                detail="Failed to get payment failure status"
            )

    async def get_user_failed_payments(
        self,
        user_id: UUID,
        page: int = 1,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get user's failed payments with retry options"""
        try:
            offset = (page - 1) * limit
            
            # Get failed payment intents
            query = select(PaymentIntent).where(
                PaymentIntent.user_id == user_id,
                PaymentIntent.status == "failed"
            ).order_by(PaymentIntent.failed_at.desc()).offset(offset).limit(limit)
            
            result = await self.db.execute(query)
            failed_payments = result.scalars().all()
            
            # Get total count
            from sqlalchemy import func
            count_result = await self.db.execute(
                select(func.count(PaymentIntent.id)).where(
                    PaymentIntent.user_id == user_id,
                    PaymentIntent.status == "failed"
                )
            )
            total = count_result.scalar()
            
            # Process each failed payment
            processed_payments = []
            
            for payment in failed_payments:
                failure_reason = PaymentFailureReason(payment.failure_reason) if payment.failure_reason else PaymentFailureReason.UNKNOWN
                retry_strategy = self._determine_retry_strategy(failure_reason, payment)
                
                processed_payments.append({
                    "payment_intent_id": str(payment.id),
                    "order_id": str(payment.order_id) if payment.order_id else None,
                    "subscription_id": str(payment.subscription_id) if payment.subscription_id else None,
                    "amount": payment.amount_breakdown.get("total", 0) if payment.amount_breakdown else 0,
                    "currency": payment.currency,
                    "failure_reason": payment.failure_reason,
                    "failed_at": payment.failed_at.isoformat() if payment.failed_at else None,
                    "retry_strategy": retry_strategy,
                    "user_message": self._get_user_friendly_message(failure_reason),
                    "can_retry": retry_strategy["should_retry"],
                    "retry_count": payment.failure_metadata.get("retry_count", 0) if payment.failure_metadata else 0
                })
            
            return {
                "failed_payments": processed_payments,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting user failed payments: {e}")
            raise HTTPException(
                status_code=500,
                detail="Failed to get failed payments"
            )
    def _categorize_stripe_error(self, error) -> PaymentFailureReason:
        """Categorize Stripe errors into failure reasons"""
        if hasattr(error, 'code'):
            error_code = error.code.lower()
            
            if error_code in ['insufficient_funds', 'balance_insufficient']:
                return PaymentFailureReason.INSUFFICIENT_FUNDS
            elif error_code in ['card_declined', 'generic_decline']:
                return PaymentFailureReason.CARD_DECLINED
            elif error_code in ['expired_card']:
                return PaymentFailureReason.EXPIRED_CARD
            elif error_code in ['incorrect_number', 'invalid_number', 'invalid_expiry_month', 'invalid_expiry_year', 'invalid_cvc']:
                return PaymentFailureReason.INVALID_CARD
            elif error_code in ['authentication_required', 'card_not_supported']:
                return PaymentFailureReason.AUTHENTICATION_REQUIRED
            elif error_code in ['processing_error']:
                return PaymentFailureReason.PROCESSING_ERROR
            elif error_code in ['rate_limit']:
                return PaymentFailureReason.LIMIT_EXCEEDED
        
        # Check error message for additional context
        error_message = str(error).lower()
        if 'fraud' in error_message or 'suspicious' in error_message:
            return PaymentFailureReason.FRAUD_SUSPECTED
        elif 'network' in error_message or 'connection' in error_message:
            return PaymentFailureReason.NETWORK_ERROR
        
        return PaymentFailureReason.UNKNOWN

    async def _record_payment_failure(
        self,
        user_id: UUID,
        order_id: Optional[UUID],
        error_code: str,
        error_message: str,
        failure_reason: PaymentFailureReason
    ):
        """Record payment failure for analytics and recovery"""
        try:
            # Create failure record in database
            failure_record = {
                "user_id": str(user_id),
                "order_id": str(order_id) if order_id else None,
                "error_code": error_code,
                "error_message": error_message,
                "failure_reason": failure_reason.value,
                "timestamp": datetime.utcnow().isoformat(),
                "retry_count": 0
            }
            
            # Store in database or send to analytics service
            logger.error(f"Payment failure recorded: {failure_record}")
            
            # Payment failure monitoring handled by hybrid task system
                
        except Exception as e:
            logger.error(f"Failed to record payment failure: {e}")