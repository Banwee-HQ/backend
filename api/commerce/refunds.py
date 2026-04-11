"""
Refunds API - Standard CRUD routes
"""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from core.db import get_db
from core.dependencies import get_current_auth_user, require_admin
from core.utils.response import Response
from models.accounts.user import User
from models.commerce.refunds import RefundStatus
from schemas.commerce.refunds import Request, UpdateRefundStatus
from services.commerce.refunds import RefundService
from core.exceptions import APIException

router = APIRouter(prefix="/refunds", tags=["refunds"])


def get_refund_service(db: AsyncSession = Depends(get_db)) -> RefundService:
    """Dependency to get refund service"""
    return RefundService(db)


async def _create_refund(
    refund_data: dict,
    current_user: User,
    refund_service: RefundService
):
    """Internal helper to create a refund request."""
    refund = await refund_service.create(user_id=current_user.id, data=refund_data)
    return Response.success(data=refund, message="Refund created successfully")


async def _list_refunds(
    refund_status: Optional[RefundStatus],
    page: int,
    limit: int,
    current_user: User,
    refund_service: RefundService
):
    """Internal helper to get user's refund history."""
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


@router.post("")
async def create(
    refund_data: dict,
    current_user: User = Depends(get_current_auth_user),
    refund_service: RefundService = Depends(get_refund_service)
):
    """Create a refund request."""
    try:
        return await _create_refund(refund_data, current_user, refund_service)
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to create refund: {str(e)}"
        )


@router.post("/")
async def create_trailing_slash(
    refund_data: dict,
    current_user: User = Depends(get_current_auth_user),
    refund_service: RefundService = Depends(get_refund_service)
):
    """Create a refund request (trailing slash variant)."""
    try:
        return await _create_refund(refund_data, current_user, refund_service)
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to create refund: {str(e)}"
        )


@router.get("")
async def list(
    refund_status: Optional[RefundStatus] = Query(None, description="Filter by refund status"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_auth_user),
    refund_service: RefundService = Depends(get_refund_service)
):
    """Get user's refund history."""
    try:
        return await _list_refunds(refund_status, page, limit, current_user, refund_service)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve refunds: {str(e)}"
        )


@router.get("/")
async def list_trailing_slash(
    refund_status: Optional[RefundStatus] = Query(None, description="Filter by refund status"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_auth_user),
    refund_service: RefundService = Depends(get_refund_service)
):
    """Get user's refund history (trailing slash variant)."""
    try:
        return await _list_refunds(refund_status, page, limit, current_user, refund_service)
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


@router.post("/orders/{order_id}/request")
async def request(
    order_id: UUID,
    refund_request: Request,
    current_user: User = Depends(get_current_auth_user),
    refund_service: RefundService = Depends(get_refund_service)
):
    """Request refund for an order."""
    try:
        refund = await refund_service.request(
            user_id=current_user.id,
            order_id=order_id,
            refund_request=refund_request
        )
        return Response.success(data=refund, message="Refund request submitted")
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to request refund: {str(e)}"
        )


# ============================================================================
# ADMIN REFUND MANAGEMENT ROUTES
# ============================================================================

@router.get("/admin/all", dependencies=[Depends(require_admin)])
async def get_all_refunds_admin(
    refund_status: Optional[RefundStatus] = Query(None, description="Filter by refund status"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all refunds (admin only)."""
    try:
        refund_service = RefundService(db)
        result = await refund_service.get_all_refunds(
            status=refund_status,
            page=page,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order
        )
        return Response.success(data=result)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch refunds: {str(e)}"
        )


@router.get("/admin/{refund_id}", dependencies=[Depends(require_admin)])
async def get_refund_details_admin(
    refund_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get refund details (admin only)."""
    try:
        refund_service = RefundService(db)
        refund = await refund_service.get_refund_details(refund_id)
        if not refund:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Refund not found"
            )
        return Response.success(data=refund)
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch refund details: {str(e)}"
        )


@router.put("/admin/{refund_id}/status", dependencies=[Depends(require_admin)])
async def update_refund_status_admin(
    refund_id: UUID,
    payload: UpdateRefundStatus,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update refund status (admin only)."""
    try:
        refund_service = RefundService(db)
        refund = await refund_service.update_status(
            refund_id=refund_id,
            status=payload.status,
            admin_notes=payload.admin_notes
        )
        return Response.success(data=refund, message="Refund status updated successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to update refund status: {str(e)}"
        )


@router.patch("/admin/{refund_id}", dependencies=[Depends(require_admin)])
async def patch_refund_admin(
    refund_id: UUID,
    payload: dict,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Partial update refund (admin only)."""
    try:
        refund_service = RefundService(db)
        refund = await refund_service.patch(refund_id, payload)
        return Response.success(data=refund, message="Refund updated successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to update refund: {str(e)}"
        )

