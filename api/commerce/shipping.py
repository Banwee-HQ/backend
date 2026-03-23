"""
Shipping routes for managing shipping methods and calculating shipping costs
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID
from core.logging import get_logger

from core.db import get_db
from core.dependencies import get_current_user, require_admin
from core.utils.response import Response
from core.errors import APIException
from models.user import User
from services.shipping import ShippingService
from schemas.shipping import (
    ShippingMethodCreate,
    ShippingMethodUpdate,
    ShippingMethodInDB
)

logger = get_logger(__name__)
router = APIRouter(prefix="/shipping", tags=["shipping"])


@router.get("/methods")
async def get_shipping_methods(
    db: AsyncSession = Depends(get_db)
):
    """
    Get all active shipping methods
    """
    try:
        shipping_service = ShippingService(db)
        methods = await shipping_service.get_all_active_shipping_methods()
        
        # Convert SQLAlchemy objects to Pydantic models
        methods_data = [ShippingMethodInDB.model_validate(method) for method in methods]
        
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
async def get_shipping_method(
    method_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific shipping method by ID"""
    try:
        shipping_service = ShippingService(db)
        method = await shipping_service.get_shipping_method_by_id(method_id)
        
        if not method:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Shipping method not found"
            )
        
        # Convert SQLAlchemy object to Pydantic model
        method_data = ShippingMethodInDB.model_validate(method)
        
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


@router.post("/methods", dependencies=[Depends(require_admin)])
async def create_shipping_method(
    method_data: ShippingMethodCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new shipping method (Admin only)"""
    try:
        shipping_service = ShippingService(db)
        method = await shipping_service.create_shipping_method(method_data)
        
        # Convert SQLAlchemy object to Pydantic model
        method_data = ShippingMethodInDB.model_validate(method)
        
        return Response.success(
            data=method_data,
            message="Shipping method created successfully"
        )
        
    except Exception as e:
        logger.error(f"Error creating shipping method: {e}")
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to create shipping method: {str(e)}"
        )


@router.put("/methods/{method_id}", dependencies=[Depends(require_admin)])
async def update_shipping_method(
    method_id: UUID,
    method_data: ShippingMethodUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a shipping method (Admin only)"""
    try:
        shipping_service = ShippingService(db)
        method = await shipping_service.update_shipping_method(method_id, method_data)
        
        if not method:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Shipping method not found"
            )
        
        # Convert SQLAlchemy object to Pydantic model
        method_data = ShippingMethodInDB.model_validate(method)
        
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


@router.delete("/methods/{method_id}", dependencies=[Depends(require_admin)])
async def delete_shipping_method(
    method_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a shipping method (Admin only)"""
    try:
        shipping_service = ShippingService(db)
        success = await shipping_service.delete_shipping_method(method_id)
        
        if not success:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Shipping method not found"
            )
        
        return Response.success(
            data={"deleted": True},
            message="Shipping method deleted successfully"
        )
        
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error deleting shipping method {method_id}: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to delete shipping method: {str(e)}"
        )


@router.post("/calculate")
async def calculate_shipping_cost(
    order_amount: float = Query(..., description="Order subtotal amount"),
    shipping_method_id: Optional[UUID] = Query(None, description="Specific shipping method ID"),
    db: AsyncSession = Depends(get_db)
):
    """
    Calculate shipping cost for a specific order amount and method
    """
    try:
        shipping_service = ShippingService(db)
        
        # Create simple address dict (country not needed for simple calculation)
        address = {'country': 'US'}
        
        cost = await shipping_service.calculate_shipping_cost(
            cart_subtotal=order_amount,
            address=address,
            shipping_method_id=shipping_method_id
        )
        
        return Response.success(
            data={
                "shipping_cost": cost,
                "order_amount": order_amount,
                "shipping_method_id": shipping_method_id
            },
            message="Shipping cost calculated successfully"
        )
        
    except Exception as e:
        logger.error(f"Error calculating shipping cost: {e}")
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to calculate shipping cost: {str(e)}"
        )