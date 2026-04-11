"""
Shipping routes for managing shipping methods and calculating shipping costs
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID
from core.logging import get_structured_logger as get_logger

from core.db import get_db
from core.dependencies import get_current_auth_user
from core.utils.response import Response
from core.exceptions import APIException
from models.accounts.user import User, UserRole
from services.commerce.shipping import ShippingService
from schemas.commerce.shipping import (
    MethodCreate,
    MethodUpdate,
    MethodInDB,
    Calculate
)

logger = get_logger(__name__)
router = APIRouter(prefix="/shipping", tags=["shipping"])


@router.get("/methods")
async def list(
    db: AsyncSession = Depends(get_db)
):
    """List all active shipping methods."""
    try:
        shipping_service = ShippingService(db)
        methods = await shipping_service.list_active()
        methods_data = [MethodInDB.model_validate(method) for method in methods]
        return Response.success(
            data=methods_data,
            message="Active shipping methods retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Error getting shipping methods: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to get shipping methods: {str(e)}"
        )


@router.get("/methods/{method_id}")
async def get(
    method_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific shipping method."""
    try:
        shipping_service = ShippingService(db)
        method = await shipping_service.get(method_id)
        if not method:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Shipping method not found"
            )
        method_data = MethodInDB.model_validate(method)
        return Response.success(
            data=method_data,
            message="Shipping method retrieved successfully"
        )
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error getting shipping method {method_id}: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to get shipping method: {str(e)}"
        )


@router.post("/methods")
async def create(
    method_data: MethodCreate,
    current_user = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a shipping method (Admin only)."""
    try:
        if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
            raise APIException(status_code=403, message="Admin access required")
        shipping_service = ShippingService(db)
        method = await shipping_service.create(method_data)
        method_data = MethodInDB.model_validate(method)
        return Response.success(
            data=method_data,
            message="Shipping method created successfully",
            code=status.HTTP_201_CREATED
        )
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error creating shipping method: {e}")
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to create shipping method: {str(e)}"
        )


@router.patch("/methods/{method_id}")
async def patch(
    method_id: UUID,
    method_data: MethodUpdate,
    current_user = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a shipping method (Admin only)."""
    try:
        if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
            raise APIException(status_code=403, message="Admin access required")
        shipping_service = ShippingService(db)
        method = await shipping_service.update(method_id, method_data)
        if not method:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Shipping method not found"
            )
        method_data = MethodInDB.model_validate(method)
        return Response.success(
            data=method_data,
            message="Shipping method updated successfully"
        )
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error updating shipping method {method_id}: {e}")
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to update shipping method: {str(e)}"
        )


@router.delete("/methods/{method_id}")
async def delete(
    method_id: UUID,
    current_user = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a shipping method (Admin only)."""
    try:
        if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
            raise APIException(status_code=403, message="Admin access required")
        shipping_service = ShippingService(db)
        await shipping_service.delete(method_id)
        return Response.success(message="Shipping method deleted successfully")
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error deleting shipping method {method_id}: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to delete shipping method: {str(e)}"
        )


# ==========================================================
# CALCULATE - Kept Route
# ==========================================================
@router.post("/calculate")
async def calc_cost(
    body: Calculate,
    db: AsyncSession = Depends(get_db)
):
    """Calculate shipping cost."""
    try:
        shipping_service = ShippingService(db)
        address = {'country': body.destination_country or 'US'}
        order_amount = body.order_amount or 0.0
        cost = await shipping_service.calc_cost(
            cart_subtotal=order_amount,
            address=address,
            shipping_method_id=body.shipping_method_id
        )
        return Response.success(
            data={
                "shipping_cost": cost,
                "order_amount": order_amount,
                "shipping_method_id": body.shipping_method_id
            },
            message="Shipping cost calculated successfully"
        )
    except Exception as e:
        logger.error(f"Error calculating shipping cost: {e}")
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to calculate shipping cost: {str(e)}"
        )


@router.get("/admin/methods")
async def list_admin(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    is_active: Optional[bool] = Query(None),
    current_user = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all shipping methods (admin only)."""
    try:
        if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
            raise APIException(status_code=403, message="Admin access required")
        shipping_service = ShippingService(db)
        methods = await shipping_service.get_all_methods(
            page=page, limit=limit, is_active=is_active
        )
        return Response.success(data=methods)
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message="Failed to fetch shipping methods")