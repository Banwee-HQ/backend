# Consolidated payment routes with 5 standard APIs per entity

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

from core.db import get_db
from core.dependencies import get_current_user
from core.utils.response import Response
from core.exceptions import APIException
from models.accounts.user import User
from services.commerce.payments import PaymentService
from schemas.commerce.payments import (
    MethodResponse,
    MethodCreate,
    MethodUpdate,
    IntentResponse,
    IntentCreate,
    TxnResponse,
    Refund
)

router = APIRouter(prefix="/payments", tags=["payments"])


# ==========================================================
# PAYMENT METHODS - 5 Standard APIs
# ==========================================================
@router.post("/methods")
async def create_method(
    payment_method_data: MethodCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new payment method"""
    service = PaymentService(db)
    method_data = {
        "type": payment_method_data.type,
        "provider": payment_method_data.provider,
        "last_four": payment_method_data.last_four,
        "expiry_month": payment_method_data.expiry_month,
        "expiry_year": payment_method_data.expiry_year,
    }
    payment_method = await service.create_method(
        user_id=current_user.id,
        stripe_payment_method_id=payment_method_data.stripe_payment_method_id,
        stripe_token=payment_method_data.stripe_token,
        payment_method_data=method_data,
        is_default=payment_method_data.is_default
    )
    return Response.success(data=MethodResponse.from_orm(payment_method), code=status.HTTP_201_CREATED)


@router.get("/methods/{payment_method_id}")
async def get_method(
    payment_method_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific payment method"""
    service = PaymentService(db)
    method = await service.get_method(payment_method_id, current_user.id)
    if not method:
        raise APIException(status_code=404, message="Payment method not found")
    return Response.success(data=MethodResponse.from_orm(method))


@router.get("/methods")
async def list_methods(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all payment methods for user"""
    service = PaymentService(db)
    payment_methods = await service.list_methods(current_user.id)
    if not payment_methods:
        payment_methods = []
    return Response.success(data=[MethodResponse.from_orm(pm) for pm in payment_methods])


@router.patch("/methods/{payment_method_id}")
async def patch_method(
    payment_method_id: UUID,
    payment_method_data: MethodUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a payment method (partial)"""
    service = PaymentService(db)
    updated_method = await service.update_method(
        payment_method_id=payment_method_id,
        user_id=current_user.id,
        update_data=payment_method_data.dict(exclude_unset=True)
    )
    if not updated_method:
        raise APIException(status_code=404, message="Payment method not found")
    return Response.success(data=MethodResponse.from_orm(updated_method))


@router.delete("/methods/{payment_method_id}")
async def delete_method(
    payment_method_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a payment method"""
    service = PaymentService(db)
    success = await service.delete_method(payment_method_id, current_user.id)
    if not success:
        raise APIException(status_code=404, message="Payment method not found")
    return Response.success(message="Payment method deleted successfully")


# ==========================================================
# PAYMENT INTENTS - 5 Standard APIs
# ==========================================================
@router.post("/intents")
async def create_intent(
    payment_intent_data: IntentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a payment intent"""
    service = PaymentService(db)
    payment_intent = await service.create_intent(
        user_id=current_user.id,
        amount=payment_intent_data.amount,
        currency=payment_intent_data.currency,
        order_id=payment_intent_data.order_id,
        subscription_id=None,
        metadata={}
    )
    return Response.success(data=IntentResponse.from_orm(payment_intent), code=status.HTTP_201_CREATED)


@router.get("/intents/{payment_intent_id}")
async def get_intent(
    payment_intent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific payment intent"""
    service = PaymentService(db)
    intent = await service.get_intent(payment_intent_id, current_user.id)
    if not intent:
        raise APIException(status_code=404, message="Payment intent not found")
    return Response.success(data=IntentResponse.from_orm(intent))


@router.get("/intents")
async def list_intents(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List payment intents for user"""
    service = PaymentService(db)
    intents = await service.list_intents(current_user.id, page=page, limit=limit)
    return Response.success(data=intents)


# ==========================================================
# TRANSACTIONS - Read Only (system creates automatically)
# ==========================================================
@router.get("/transactions/{transaction_id}")
async def get_transaction(
    transaction_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific transaction"""
    service = PaymentService(db)
    transaction = await service.get_transaction(transaction_id, current_user.id)
    if not transaction:
        raise APIException(status_code=404, message="Transaction not found")
    return Response.success(data=TxnResponse.from_orm(transaction))


@router.get("/transactions")
async def list_transactions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List transactions for user"""
    service = PaymentService(db)
    transactions = await service.transactions(current_user.id, page=page, limit=limit)
    return Response.success(data=transactions)


# ==========================================================
# REFUNDS - Create & List Only (immutable after processing)
# ==========================================================
@router.post("/refunds")
async def create_refund(
    request: Refund,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a refund"""
    from models.accounts.user import UserRole
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise APIException(status_code=403, message="Only admins can create refunds")
    
    service = PaymentService(db)
    transaction = await service.refund(
        payment_intent_id=request.payment_intent_id,
        amount=request.amount,
        reason=request.reason
    )
    return Response.success(data=TxnResponse.from_orm(transaction), code=status.HTTP_201_CREATED)


@router.get("/refunds/{refund_id}")
async def get_refund(
    refund_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific refund"""
    service = PaymentService(db)
    refund = await service.get_refund(refund_id, current_user.id)
    if not refund:
        raise APIException(status_code=404, message="Refund not found")
    return Response.success(data=TxnResponse.from_orm(refund))


@router.get("/refunds")
async def list_refunds(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List refunds for user"""
    service = PaymentService(db)
    refunds = await service.list_refunds(current_user.id, page=page, limit=limit)
    return Response.success(data=refunds)


# ==========================================================
# KEPT ROUTES - Additional functionality
# ==========================================================
@router.post("/intents/{payment_intent_id}/confirm")
async def confirm_intent(
    payment_intent_id: UUID,
    payment_method_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Confirm a payment intent"""
    service = PaymentService(db)
    payment_intent = await service.confirm_intent(
        payment_intent_id=payment_intent_id,
        payment_method_id=payment_method_id
    )
    return Response.success(data=IntentResponse.from_orm(payment_intent))


@router.post("/methods/{payment_method_id}/default")
async def set_default_method(
    payment_method_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Set a payment method as default"""
    service = PaymentService(db)
    success = await service.set_default_method(payment_method_id, current_user.id)
    if not success:
        raise APIException(status_code=404, message="Payment method not found")
    return Response.success(message="Payment method set as default successfully")


@router.post("/process")
async def process_payment(
    amount: float,
    payment_method_id: UUID,
    order_id: Optional[UUID] = None,
    subscription_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Process a payment"""
    service = PaymentService(db)
    result = await service.process(
        user_id=current_user.id,
        amount=amount,
        payment_method_id=payment_method_id,
        order_id=order_id,
        subscription_id=subscription_id
    )
    return Response.success(data=result)


# ==========================================================
# FAILURE HANDLING - Kept routes
# ==========================================================
@router.get("/failures/{payment_intent_id}/status")
async def failure_status(
    payment_intent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed status of a failed payment"""
    service = PaymentService(db)
    failure_details = await service.failure_status(payment_intent_id, current_user.id)
    return Response.success(data=failure_details, message="Payment failure details retrieved")


@router.post("/failures/{payment_intent_id}/retry")
async def retry_payment(
    payment_intent_id: UUID,
    new_payment_method_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Retry a failed payment"""
    service = PaymentService(db)
    retry_result = await service.retry(payment_intent_id, new_payment_method_id)
    return Response.success(data=retry_result, message="Payment retry initiated")


@router.get("/failures")
async def list_failures(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List user's failed payments"""
    service = PaymentService(db)
    failed_payments = await service.failed_payments(current_user.id, page=page, limit=limit)
    return Response.success(data=failed_payments)