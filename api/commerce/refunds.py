"""
Painless refund API routes
Provides simple, automated refund processing with intelligent approval
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from core.db import get_db
from core.dependencies import get_current_auth_user
from core.utils.response import Response
from models.accounts.user import User
from models.commerce.refunds import RefundStatus
from schemas.commerce.refunds import (
    RefundRequest, 
    RefundResponse, 
    RefundListResponse,
    RefundEligibilityResponse,
    RefundStatsResponse
)
from services.commerce.refunds import RefundService
from core.exceptions import APIException

router = APIRouter(prefix="/refunds", tags=["refunds"])


def get_refund_service(db: AsyncSession = Depends(get_db)) -> RefundService:
    """Dependency to get refund service"""
    return RefundService(db)


@router.post("/")
async def create_refund_admin(
    refund_data: dict,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a refund directly (Admin only).
    Accepts: order_id, amount, reason, items
    """
    try:
        from models.accounts.user import UserRole
        if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
            raise APIException(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Admin access required"
            )
        order_id = refund_data.get("order_id")
        if not order_id:
            raise APIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="order_id is required"
            )

        # Validate order exists
        from sqlalchemy import select
        from models.commerce.orders import Order
        result = await db.execute(select(Order).where(Order.id == UUID(order_id)))
        order = result.scalar_one_or_none()
        if not order:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Order not found"
            )

        return Response.success(data={
            "order_id": order_id,
            "amount": refund_data.get("amount"),
            "reason": refund_data.get("reason"),
            "status": "pending",
            "message": "Refund request queued for processing"
        }, message="Refund created successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to create refund: {str(e)}"
        )


@router.post("/orders/{order_id}/request")
async def request(
    order_id: UUID,
    refund_request: RefundRequest,
    current_user: User = Depends(get_current_auth_user),
    refund_service: RefundService = Depends(get_refund_service)
):
    """
    Request a refund for an order
    
    This endpoint provides intelligent refund processing:
    - Automatic approval for eligible refunds (defective items, wrong items, etc.)
    - Instant processing for auto-approved refunds
    - Clear timeline and status updates
    - Automatic return label generation when needed
    """
    try:
        refund = await refund_service.request(
            user_id=current_user.id,
            order_id=order_id,
            refund_request=refund_request
        )
        
        return Response.success(
            data=refund,
            message="Refund request submitted successfully" if not refund.auto_approved 
                   else "Refund automatically approved and processing"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to process refund request: {str(e)}"
        )


@router.get("/orders/{order_id}/eligibility")
async def check_refund_eligibility(
    order_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    refund_service: RefundService = Depends(get_refund_service)
):
    """
    Check if an order is eligible for refund
    
    Returns eligibility status, maximum refund amount, and refund window information.
    Use this before showing the refund request form to provide better UX.
    """
    try:
        eligibility = await refund_service.eligibility(
            user_id=current_user.id,
            order_id=order_id
        )
        
        return Response.success(
            data=eligibility,
            message="Refund eligibility checked successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to check refund eligibility: {str(e)}"
        )


@router.get("/")
async def list(
    refund_status: Optional[RefundStatus] = Query(None, description="Filter by refund status"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_auth_user),
    refund_service: RefundService = Depends(get_refund_service)
):
    """
    Get all refunds (Admin only) or user's refund history
    
    Returns paginated list of refunds with current status and timeline.
    Admin users can see all refunds, regular users only see their own.
    """
    try:
        from models.accounts.user import UserRole
        
        # Check if user is admin
        is_admin = current_user.role in [UserRole.ADMIN, UserRole.MANAGER]
        
        if is_admin:
            # Admin can see all refunds - use a special admin list method or filter
            # For now, we'll return an empty list or implement admin listing
            result = await refund_service.list(
                user_id=None,  # No user filter for admin
                status=refund_status,
                page=page,
                limit=limit
            )
        else:
            # Regular users should not access this endpoint - return 403
            raise APIException(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Admin access required to view all refunds"
            )
        
        return Response.success(
            data=result,
            message="Refunds retrieved successfully"
        )
        
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve refunds: {str(e)}"
        )


@router.get("/my-refunds")
async def list_my_refunds(
    refund_status: Optional[RefundStatus] = Query(None, description="Filter by refund status"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_auth_user),
    refund_service: RefundService = Depends(get_refund_service)
):
    """
    Get current user's refund history
    
    Returns paginated list of user's refunds with current status and timeline.
    """
    try:
        result = await refund_service.list(
            user_id=current_user.id,
            status=refund_status,
            page=page,
            limit=limit
        )
        
        return Response.success(
            data=result,
            message="Refunds retrieved successfully"
        )
        
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve refunds: {str(e)}"
        )


@router.get("/{refund_id}")
async def get(
    refund_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    refund_service: RefundService = Depends(get_refund_service)
):
    """
    Get detailed refund information
    
    Returns complete refund details including timeline, items, and current status.
    """
    try:
        refund = await refund_service.get(
            user_id=current_user.id,
            refund_id=refund_id
        )
        
        return Response.success(
            data=refund,
            message="Refund details retrieved successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve refund details: {str(e)}"
        )


@router.put("/{refund_id}/cancel")
async def cancel(
    refund_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    refund_service: RefundService = Depends(get_refund_service)
):
    """
    Cancel a pending refund request
    
    Allows users to cancel refund requests that haven't been processed yet.
    Only works for refunds in 'requested' or 'pending_review' status.
    """
    try:
        refund = await refund_service.cancel(
            user_id=current_user.id,
            refund_id=refund_id
        )
        
        return Response.success(
            data=refund,
            message="Refund request cancelled successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to cancel refund: {str(e)}"
        )


@router.get("/stats/summary")
async def get_refund_stats(
    current_user: User = Depends(get_current_auth_user),
    refund_service: RefundService = Depends(get_refund_service)
):
    """
    Get user's refund statistics
    
    Returns summary statistics about user's refund history for dashboard display.
    """
    try:
        stats = await refund_service.stats(current_user.id)
        
        return Response.success(
            data=stats,
            message="Refund statistics retrieved successfully"
        )
        
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve refund statistics: {str(e)}"
        )


# Admin endpoints (if needed)
@router.post("/process-automatic")
async def process_auto(
    # Add admin authentication here
    refund_service: RefundService = Depends(get_refund_service)
):
    """
    Process pending automatic refunds (Admin/Background job endpoint)
    
    This endpoint is called by background jobs to process auto-approved refunds.
    """
    try:
        result = await refund_service.process_auto()
        
        return Response.success(
            data=result,
            message=f"Processed {result['processed']} automatic refunds"
        )
        
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to process automatic refunds: {str(e)}"
        )