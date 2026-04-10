"""
Refunds API - Standard CRUD routes
"""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from core.db import get_db
from core.dependencies import get_current_auth_user
from core.utils.response import Response
from models.accounts.user import User
from models.commerce.refunds import RefundStatus
from schemas.commerce.refunds import Request
from services.commerce.refunds import RefundService
from core.exceptions import APIException

router = APIRouter(prefix="/refunds", tags=["refunds"])


def get_refund_service(db: AsyncSession = Depends(get_db)) -> RefundService:
    """Dependency to get refund service"""
    return RefundService(db)


@router.post("/")
async def create(
    refund_data: dict,
    current_user: User = Depends(get_current_auth_user),
    refund_service: RefundService = Depends(get_refund_service)
):
    """Create a refund request."""
    try:
        refund = await refund_service.create(user_id=current_user.id, data=refund_data)
        return Response.success(data=refund, message="Refund created successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to create refund: {str(e)}"
        )


@router.get("/")
async def list(
    refund_status: Optional[RefundStatus] = Query(None, description="Filter by refund status"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_auth_user),
    refund_service: RefundService = Depends(get_refund_service)
):
    """Get user's refund history."""
    try:
        result = await refund_service.list(
            user_id=current_user.id,
            status=refund_status,
            page=page,
            limit=limit
        )
        if isinstance(result, dict) and "items" in result:
            pagination = {
                "page": result.get("page", page),
                "limit": result.get("limit", limit),
                "total": result.get("total", 0),
                "pages": result.get("pages", 1)
            }
            return Response.success(data=result.get("items", []), pagination=pagination, message="Refunds retrieved successfully")
        return Response.success(data=result, message="Refunds retrieved successfully")
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
    """Get refund by ID."""
    try:
        refund = await refund_service.get(user_id=current_user.id, refund_id=refund_id)
        if not refund:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Refund not found"
            )
        return Response.success(data=refund, message="Refund retrieved successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve refund: {str(e)}"
        )


@router.post("/orders/{order_id}")
async def request(
    order_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_auth_user),
    refund_service: RefundService = Depends(get_refund_service)
):
    """Request refund for an order."""
    try:
        refund = await refund_service.request(
            user_id=current_user.id,
            order_id=order_id,
            refund_request=request
        )
        return Response.success(data=refund, message="Refund request submitted")
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to request refund: {str(e)}"
        )

