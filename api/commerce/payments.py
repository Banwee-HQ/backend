# Consolidated payment routes with 5 standard APIs per entity

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

from core.db import get_db
from core.dependencies import get_current_auth_user, require_admin, get_current_auth_user
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


@router.get("/")
async def overview(current_user: User = Depends(get_current_auth_user), db: AsyncSession = Depends(get_db)):
    """Overview endpoint for payments - kept for compatibility with older clients/tests."""
    try:
        service = PaymentService(db)
        # Return a lightweight overview if available, otherwise empty dict
        overview_data = {}
        try:
            if hasattr(service, 'overview'):
                overview_data = await service.overview(current_user.id)
        except Exception:
            overview_data = {}
        return Response.success(data=overview_data)
    except Exception as e:
        raise APIException(status_code=500, message=str(e))


# ==========================================================
# PAYMENT METHODS - 5 Standard APIs
# ==========================================================
@router.post("/methods/")
async def create_method(
    payment_method_data: MethodCreate,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new payment method"""
    try:
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
        return Response.success(data=MethodResponse.from_orm(payment_method), code=status.HTTP_201_CREATED, message="Payment method created successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message=f"Failed to create payment method: {str(e)}")


@router.get("/methods/{payment_method_id}/")
async def get_method(
    payment_method_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific payment method"""
    try:
        service = PaymentService(db)
        method = await service.get(payment_method_id, current_user.id)
        if not method:
            raise APIException(status_code=404, message="Payment method not found")
        return Response.success(data=MethodResponse.from_orm(method), message="Payment method retrieved successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message=f"Failed to get payment method: {str(e)}")


@router.get("/methods/")
async def list_methods(
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """List all payment methods for user"""
    try:
        service = PaymentService(db)
        payment_methods = await service.list(current_user.id)
        if not payment_methods:
            payment_methods = []
        return Response.success(data=[MethodResponse.from_orm(pm) for pm in payment_methods])
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message=f"Failed to list payment methods: {str(e)}")


@router.patch("/methods/{payment_method_id}/")
async def patch_method(
    payment_method_id: UUID,
    payment_method_data: MethodUpdate,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a payment method (partial)"""
    try:
        service = PaymentService(db)
        updated_method = await service.update(
            payment_method_id,
            current_user.id,
            payment_method_data.dict(exclude_unset=True)
        )
        if not updated_method:
            raise APIException(status_code=404, message="Payment method not found")
        return Response.success(data=MethodResponse.from_orm(updated_method), message="Payment method updated successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message=f"Failed to update payment method: {str(e)}")


@router.delete("/methods/{payment_method_id}/")
async def delete_method(
    payment_method_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a payment method"""
    try:
        service = PaymentService(db)
        success = await service.delete(payment_method_id, current_user.id)
        if not success:
            raise APIException(status_code=404, message="Payment method not found")
        return Response.success(message="Payment method deleted successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message=f"Failed to delete payment method: {str(e)}")


# ==========================================================
# PAYMENT INTENTS - 5 Standard APIs
# ==========================================================
@router.post("/intents/")
async def create_intent(
    payment_intent_data: IntentCreate,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a payment intent"""
    try:
        service = PaymentService(db)
        payment_intent = await service.create_intent(
            user_id=current_user.id,
            amount=payment_intent_data.amount,
            currency=payment_intent_data.currency,
            order_id=payment_intent_data.order_id,
            subscription_id=None,
            metadata={}
        )
        return Response.success(data=IntentResponse.from_orm(payment_intent), code=status.HTTP_201_CREATED, message="Payment intent created successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message=f"Failed to create payment intent: {str(e)}")


@router.get("/intents/{payment_intent_id}/")
async def get_intent(
    payment_intent_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific payment intent"""
    try:
        service = PaymentService(db)
        intent = await service.get_intent(payment_intent_id, current_user.id)
        if not intent:
            raise APIException(status_code=404, message="Payment intent not found")
        return Response.success(data=IntentResponse.from_orm(intent), message="Payment intent retrieved successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message=f"Failed to get payment intent: {str(e)}")


@router.get("/intents/")
async def list_intents(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """List payment intents for user"""
    try:
        service = PaymentService(db)
        result = await service.list_intents(current_user.id, page=page, limit=limit)
        if isinstance(result, dict) and "items" in result:
            pagination = {
                "page": result.get("page", page),
                "limit": result.get("limit", limit),
                "total": result.get("total", 0),
                "pages": (result.get("total", 0) + limit - 1) // limit
            }
            return Response.success(data=[IntentResponse.from_orm(i) for i in result.get("items", [])], pagination=pagination)
        return Response.success(data=result)
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message=f"Failed to list payment intents: {str(e)}")


# ==========================================================
# TRANSACTIONS - Read Only (system creates automatically)
# ==========================================================
@router.get("/transactions/{transaction_id}/")
async def get_transaction(
    transaction_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific transaction"""
    try:
        service = PaymentService(db)
        transaction = await service.get_transaction(transaction_id, current_user.id)
        if not transaction:
            raise APIException(status_code=404, message="Transaction not found")
        return Response.success(data=TxnResponse.from_orm(transaction), message="Transaction retrieved successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message=f"Failed to get transaction: {str(e)}")


@router.get("/transactions/")
async def list_transactions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """List transactions for user"""
    try:
        service = PaymentService(db)
        result = await service.transactions(current_user.id, page=page, limit=limit)
        if isinstance(result, dict) and "items" in result:
            pagination = {
                "page": result.get("page", page),
                "limit": result.get("limit", limit),
                "total": result.get("total", 0),
                "pages": (result.get("total", 0) + limit - 1) // limit
            }
            return Response.success(data=[TxnResponse.from_orm(t) for t in result.get("items", [])], pagination=pagination)
        return Response.success(data=result)
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message=f"Failed to list transactions: {str(e)}")


# ==========================================================
# REFUNDS - Create & List Only (immutable after processing)
# ==========================================================
@router.post("/refunds/")
async def create_refund(
    request: Refund,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a refund"""    
    try:
        service = PaymentService(db)
        transaction = await service.refund(
            payment_intent_id=request.payment_intent_id,
            amount=request.amount,
            reason=request.reason
        )
        return Response.success(data=TxnResponse.from_orm(transaction), message="Refund created successfully", status_code=status.HTTP_201_CREATED)
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message=f"Failed to create refund: {str(e)}")


@router.get("/refunds/{refund_id}/")
async def get_refund(
    refund_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific refund"""
    try:
        service = PaymentService(db)
        refund = await service.get_refund(refund_id, current_user.id)
        if not refund:
            raise APIException(status_code=404, message="Refund not found")
        return Response.success(data=TxnResponse.from_orm(refund), message="Refund retrieved successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message=f"Failed to get refund: {str(e)}")


@router.get("/refunds/")
async def list_refunds(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """List refunds for user"""
    try:
        service = PaymentService(db)
        result = await service.list_refunds(current_user.id, page=page, limit=limit)
        if isinstance(result, dict) and "items" in result:
            pagination = {
                "page": result.get("page", page),
                "limit": result.get("limit", limit),
                "total": result.get("total", 0),
                "pages": (result.get("total", 0) + limit - 1) // limit
            }
            return Response.success(data=result.get("items", []), pagination=pagination)
        return Response.success(data=result)
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message=f"Failed to list refunds: {str(e)}")


# ==========================================================
# KEPT ROUTES - Additional functionality
# ==========================================================
@router.post("/intents/{payment_intent_id}/confirm/")
async def confirm_intent(
    payment_intent_id: UUID,
    payment_method_id: str,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Confirm a payment intent"""
    try:
        service = PaymentService(db)
        payment_intent = await service.confirm_intent(
            payment_intent_id=payment_intent_id,
            payment_method_id=payment_method_id
        )
        return Response.success(data=IntentResponse.from_orm(payment_intent), message="Payment intent confirmed successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message=f"Failed to confirm payment intent: {str(e)}")


@router.post("/methods/{payment_method_id}/default/")
async def set_default_method(
    payment_method_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Set a payment method as default"""
    try:
        service = PaymentService(db)
        success = await service.set_default(payment_method_id, current_user.id)
        if not success:
            raise APIException(status_code=404, message="Payment method not found")
        return Response.success(message="Payment method set as default successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message=f"Failed to set default payment method: {str(e)}")


@router.post("/process/")
async def process_payment(
    amount: float,
    payment_method_id: UUID,
    order_id: Optional[UUID] = None,
    subscription_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Process a payment"""
    try:
        service = PaymentService(db)
        result = await service.process(
            user_id=current_user.id,
            amount=amount,
            payment_method_id=payment_method_id,
            order_id=order_id,
            subscription_id=subscription_id
        )
        return Response.success(data=result, message="Payment processed successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message=f"Failed to process payment: {str(e)}")


# ==========================================================
# FAILURE HANDLING - Kept routes
# ==========================================================
@router.get("/failures/{payment_intent_id}/status/")
async def failure_status(
    payment_intent_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed status of a failed payment"""
    try:
        service = PaymentService(db)
        failure_details = await service.failure_status(payment_intent_id, current_user.id)
        return Response.success(data=failure_details, message="Payment failure details retrieved")
    except HTTPException as e:
        raise APIException(status_code=e.status_code, message=e.detail)
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to get failure status: {str(e)}")


@router.post("/failures/{payment_intent_id}/retry/")
async def retry_payment(
    payment_intent_id: UUID,
    new_payment_method_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Retry a failed payment"""
    try:
        service = PaymentService(db)
        retry_result = await service.retry(payment_intent_id, new_payment_method_id)
        return Response.success(data=retry_result, message="Payment retry initiated")
    except HTTPException as e:
        raise APIException(status_code=e.status_code, message=e.detail)
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to retry payment: {str(e)}")


@router.get("/failures/")
async def list_failures(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """List user's failed payments"""
    service = PaymentService(db)
    result = await service.failed_payments(current_user.id, page=page, limit=limit)
    if isinstance(result, dict) and "pagination" in result:
        return Response.success(data=result.get("failed_payments", []), pagination=result.get("pagination"))
    return Response.success(data=result)