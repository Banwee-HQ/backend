# Consolidated payment routes
# This file includes all payment-related routes

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from core.db import get_db
from core.dependencies import get_current_user
from core.utils.response import Response
from models.user import User
from services.payments import PaymentService
from schemas.payments import (
    PaymentMethodResponse,
    PaymentMethodCreate,
    PaymentMethodUpdate,
    PaymentIntentResponse,
    PaymentIntentCreate,
    TransactionResponse
)

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("/")
async def get_payments_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get payments overview for current user"""
    service = PaymentService(db)
    payment_methods = await service.get_user_payment_methods(current_user.id)
    return Response.success(
        data={
            "payment_methods": [PaymentMethodResponse.from_orm(pm) for pm in payment_methods],
            "total_methods": len(payment_methods) if payment_methods else 0
        },
        message="Payments overview retrieved"
    )


@router.get("/methods")
async def get_payment_methods(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's payment methods"""
    service = PaymentService(db)
    payment_methods = await service.get_user_payment_methods(current_user.id)
    # Always return an array, even if empty
    if not payment_methods:
        payment_methods = []
    
    return Response.success(data=[PaymentMethodResponse.from_orm(pm) for pm in payment_methods])


@router.post("/methods")
async def create_payment_method(
    payment_method_data: PaymentMethodCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new payment method"""
    service = PaymentService(db)
    
    # Prepare payment method data for the service
    method_data = {
        "type": payment_method_data.type,
        "provider": payment_method_data.provider,
        "last_four": payment_method_data.last_four,
        "expiry_month": payment_method_data.expiry_month,
        "expiry_year": payment_method_data.expiry_year,
    }
    
    payment_method = await service.create_payment_method(
        user_id=current_user.id,
        stripe_payment_method_id=payment_method_data.stripe_payment_method_id,
        stripe_token=payment_method_data.stripe_token,
        payment_method_data=method_data,
        is_default=payment_method_data.is_default
    )
    return Response.success(data=PaymentMethodResponse.from_orm(payment_method))


@router.delete("/methods/{payment_method_id}")
async def delete_payment_method(
    payment_method_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a payment method"""
    service = PaymentService(db)
    success = await service.delete_payment_method(payment_method_id, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment method not found"
        )
    
    return {"message": "Payment method deleted successfully"}


@router.put("/methods/{payment_method_id}")
async def update_payment_method(
    payment_method_id: UUID,
    payment_method_data: PaymentMethodUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a payment method"""
    service = PaymentService(db)
    updated_method = await service.update_payment_method(
        payment_method_id=payment_method_id,
        user_id=current_user.id,
        update_data=payment_method_data.dict(exclude_unset=True)
    )
    if not updated_method:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment method not found"
        )
    return Response.success(data=PaymentMethodResponse.from_orm(updated_method))


@router.put("/methods/{payment_method_id}/default")
async def set_default_payment_method(
    payment_method_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Set a payment method as default"""
    service = PaymentService(db)
    success = await service.set_default_payment_method(payment_method_id, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment method not found"
        )
    
    return {"message": "Payment method set as default successfully"}


@router.post("/intents")
async def create_payment_intent(
    payment_intent_data: PaymentIntentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a payment intent"""
    service = PaymentService(db)
    payment_intent = await service.create_payment_intent(
        user_id=current_user.id,
        amount=payment_intent_data.amount,
        currency=payment_intent_data.currency,
        order_id=payment_intent_data.order_id,
        subscription_id=None,  # Not provided in schema
        metadata={}  # Default empty metadata
    )
    return Response.success(data=PaymentIntentResponse.from_orm(payment_intent))


@router.post("/intents/{payment_intent_id}/confirm")
async def confirm_payment_intent(
    payment_intent_id: UUID,
    payment_method_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Confirm a payment intent"""
    service = PaymentService(db)
    payment_intent = await service.confirm_payment_intent(
        payment_intent_id=payment_intent_id,
        payment_method_id=payment_method_id
    )
    return Response.success(data=PaymentIntentResponse.from_orm(payment_intent))


@router.post("/process")
async def process_payment(
    amount: float,
    payment_method_id: UUID,
    order_id: Optional[UUID] = None,
    subscription_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Process a payment (simplified)"""
    service = PaymentService(db)
    result = await service.process_payment(
        user_id=current_user.id,
        amount=amount,
        payment_method_id=payment_method_id,
        order_id=order_id,
        subscription_id=subscription_id
    )
    return result


@router.get("/transactions")
async def get_user_transactions(
    page: int = 1,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user transaction history"""
    service = PaymentService(db)
    transactions = await service.get_user_transactions(
        user_id=current_user.id,
        page=page,
        limit=limit
    )
    return Response.success(data=transactions)


@router.post("/refunds/{payment_intent_id}")
async def create_refund(
    payment_intent_id: UUID,
    amount: Optional[float] = None,
    reason: str = "requested_by_customer",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a refund for a payment (admin only)"""
    if current_user.role != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create refunds"
        )
    
    service = PaymentService(db)
    transaction = await service.create_refund(
        payment_intent_id=payment_intent_id,
        amount=amount,
        reason=reason
    )
    return Response.success(data=TransactionResponse.from_orm(transaction))

# ============================================================================
# PAYMENT FAILURE HANDLING ROUTES
# ============================================================================

@router.get("/failures/{payment_intent_id}/status")
async def get_payment_failure_status(
    payment_intent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed status of a failed payment"""
    try:
        service = PaymentService(db)
        failure_details = await service.get_payment_failure_status(
            payment_intent_id=payment_intent_id,
            user_id=current_user.id
        )
        return Response.success(
            data=failure_details,
            message="Payment failure details retrieved"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to get payment failure status"
        )


@router.post("/failures/{payment_intent_id}/retry")
async def retry_failed_payment(
    payment_intent_id: UUID,
    new_payment_method_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Retry a failed payment with optional new payment method"""
    try:
        service = PaymentService(db)
        
        # Verify payment intent belongs to user first
        failure_details = await service.get_payment_failure_status(
            payment_intent_id=payment_intent_id,
            user_id=current_user.id
        )
        
        # Retry the payment
        retry_result = await service.retry_failed_payment(
            payment_intent_id=payment_intent_id,
            new_payment_method_id=new_payment_method_id
        )
        
        return Response.success(
            data=retry_result,
            message="Payment retry initiated successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to retry payment"
        )


@router.get("/failures/user/failed-payments")
async def get_user_failed_payments(
    page: int = 1,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's failed payments with retry options"""
    try:
        service = PaymentService(db)
        failed_payments_data = await service.get_user_failed_payments(
            user_id=current_user.id,
            page=page,
            limit=limit
        )
        
        return Response.success(
            data=failed_payments_data,
            message="Failed payments retrieved successfully"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to get failed payments"
        )


@router.post("/failures/{payment_intent_id}/abandon")
async def abandon_failed_payment(
    payment_intent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Abandon a failed payment (mark as permanently failed)"""
    try:
        from models.payments import PaymentIntent
        from sqlalchemy import select
        
        # Get payment intent with lock
        result = await db.execute(
            select(PaymentIntent).where(
                PaymentIntent.id == payment_intent_id,
                PaymentIntent.user_id == current_user.id
            ).with_for_update()
        )
        payment_intent = result.scalar_one_or_none()
        
        if not payment_intent:
            raise HTTPException(
                status_code=404,
                detail="Payment intent not found"
            )
        
        if payment_intent.status != "failed":
            raise HTTPException(
                status_code=400,
                detail="Can only abandon failed payments"
            )
        
        # Mark as abandoned
        payment_intent.status = "abandoned"
        if not payment_intent.failure_metadata:
            payment_intent.failure_metadata = {}
        payment_intent.failure_metadata["abandoned_at"] = datetime.utcnow().isoformat()
        payment_intent.failure_metadata["abandoned_by_user"] = True
        
        await db.commit()
        
        return Response.success(
            data={
                "payment_intent_id": str(payment_intent_id),
                "status": "abandoned"
            },
            message="Payment marked as abandoned"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to abandon payment"
        )


@router.get("/failures/analytics/failure-reasons")
async def get_failure_analytics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get analytics on payment failure reasons for the user"""
    try:
        from models.payments import PaymentIntent
        from sqlalchemy import select, func
        from services.payments import PaymentFailureReason
        
        # Get failure reason distribution
        result = await db.execute(
            select(
                PaymentIntent.failure_reason,
                func.count(PaymentIntent.id).label("count")
            ).where(
                PaymentIntent.user_id == current_user.id,
                PaymentIntent.status.in_(["failed", "abandoned"])
            ).group_by(PaymentIntent.failure_reason)
        )
        
        failure_reasons = result.all()
        
        # Process results
        service = PaymentService(db)
        analytics = {
            "failure_distribution": [],
            "total_failed_payments": 0,
            "recommendations": []
        }
        
        total_failures = 0
        for reason, count in failure_reasons:
            total_failures += count
            
            try:
                failure_enum = PaymentFailureReason(reason) if reason else PaymentFailureReason.UNKNOWN
                user_message = service._get_user_friendly_message(failure_enum)
                next_steps = service._get_next_steps(failure_enum)
            except ValueError:
                failure_enum = PaymentFailureReason.UNKNOWN
                user_message = "Unknown payment issue"
                next_steps = ["Contact support for assistance"]
            
            analytics["failure_distribution"].append({
                "reason": reason or "unknown",
                "count": count,
                "percentage": 0,  # Will calculate after getting total
                "user_message": user_message,
                "recommended_actions": next_steps
            })
        
        # Calculate percentages
        for item in analytics["failure_distribution"]:
            item["percentage"] = round((item["count"] / total_failures * 100), 2) if total_failures > 0 else 0
        
        analytics["total_failed_payments"] = total_failures
        
        # Generate recommendations based on most common failures
        if analytics["failure_distribution"]:
            most_common = max(analytics["failure_distribution"], key=lambda x: x["count"])
            analytics["recommendations"] = most_common["recommended_actions"]
        
        return Response.success(
            data=analytics,
            message="Payment failure analytics retrieved"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to get failure analytics"
        )