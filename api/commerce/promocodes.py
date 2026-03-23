from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from uuid import UUID
from core.db import get_db
from core.utils.response import Response
from core.errors import APIException
from schemas.promos import PromocodeCreate, PromocodeUpdate
from services.promocode import PromocodeService
from models.user import User
from core.dependencies import get_current_auth_user
from fastapi.security import OAuth2PasswordBearer

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


@router.get("/")
async def get_all_promocodes(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    is_active: Optional[bool] = Query(None),
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all promocodes (Admin only)."""
    try:
        if current_user.role != "Admin":
            raise APIException(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Only admins can view promocodes"
            )
        
        promocode_service = PromocodeService(db)
        promocodes = await promocode_service.get_all_promocodes()
        
        # Filter by active status if provided
        if is_active is not None:
            promocodes = [p for p in promocodes if p.is_active == is_active]
        
        # Simple pagination
        start = (page - 1) * limit
        end = start + limit
        paginated_promocodes = promocodes[start:end]
        
        return Response.success(data={
            "promocodes": [
                {
                    "id": str(p.id),
                    "code": p.code,
                    "description": p.description,
                    "discount_type": p.discount_type,
                    "value": p.value,
                    "minimum_order_amount": p.minimum_order_amount,
                    "maximum_discount_amount": p.maximum_discount_amount,
                    "usage_limit": p.usage_limit,
                    "used_count": p.used_count,
                    "is_active": p.is_active,
                    "valid_from": p.valid_from.isoformat() if p.valid_from else None,
                    "valid_until": p.valid_until.isoformat() if p.valid_until else None,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None
                }
                for p in paginated_promocodes
            ],
            "pagination": {
                "current_page": page,
                "limit": limit,
                "total": len(promocodes),
                "pages": (len(promocodes) + limit - 1) // limit
            }
        })
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch promocodes: {str(e)}"
        )


@router.get("/{promocode_id}")
async def get_promocode_by_id(
    promocode_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get promocode by ID (Admin only)."""
    try:
        if current_user.role != "Admin":
            raise APIException(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Only admins can view promocodes"
            )
        
        promocode_service = PromocodeService(db)
        promocode = await promocode_service.get_promocode_by_id(promocode_id)
        
        if not promocode:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Promocode not found"
            )
        
        return Response.success(data={
            "id": str(promocode.id),
            "code": promocode.code,
            "description": promocode.description,
            "discount_type": promocode.discount_type,
            "value": promocode.value,
            "minimum_order_amount": promocode.minimum_order_amount,
            "maximum_discount_amount": promocode.maximum_discount_amount,
            "usage_limit": promocode.usage_limit,
            "used_count": promocode.used_count,
            "is_active": promocode.is_active,
            "valid_from": promocode.valid_from.isoformat() if promocode.valid_from else None,
            "valid_until": promocode.valid_until.isoformat() if promocode.valid_until else None,
            "created_at": promocode.created_at.isoformat() if promocode.created_at else None,
            "updated_at": promocode.updated_at.isoformat() if promocode.updated_at else None
        })
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch promocode: {str(e)}"
        )


@router.post("/")
async def create_promocode(
    promocode_data: PromocodeCreate,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Create new promocode (Admin only)."""
    try:
        if current_user.role != "Admin":
            raise APIException(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Only admins can create promocodes"
            )
        
        promocode_service = PromocodeService(db)
        promocode = await promocode_service.create_promocode(promocode_data)
        
        return Response.success(data={
            "id": str(promocode.id),
            "code": promocode.code,
            "description": promocode.description,
            "discount_type": promocode.discount_type,
            "value": promocode.value,
            "minimum_order_amount": promocode.minimum_order_amount,
            "maximum_discount_amount": promocode.maximum_discount_amount,
            "usage_limit": promocode.usage_limit,
            "used_count": promocode.used_count,
            "is_active": promocode.is_active,
            "valid_from": promocode.valid_from.isoformat() if promocode.valid_from else None,
            "valid_until": promocode.valid_until.isoformat() if promocode.valid_until else None,
            "created_at": promocode.created_at.isoformat() if promocode.created_at else None,
            "updated_at": promocode.updated_at.isoformat() if promocode.updated_at else None
        }, message="Promocode created successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to create promocode: {str(e)}"
        )


@router.put("/{promocode_id}")
async def update_promocode(
    promocode_id: UUID,
    promocode_data: PromocodeUpdate,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Update promocode (Admin only)."""
    try:
        if current_user.role != "Admin":
            raise APIException(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Only admins can update promocodes"
            )
        
        promocode_service = PromocodeService(db)
        promocode = await promocode_service.update_promocode(promocode_id, promocode_data)
        
        return Response.success(data={
            "id": str(promocode.id),
            "code": promocode.code,
            "description": promocode.description,
            "discount_type": promocode.discount_type,
            "value": promocode.value,
            "minimum_order_amount": promocode.minimum_order_amount,
            "maximum_discount_amount": promocode.maximum_discount_amount,
            "usage_limit": promocode.usage_limit,
            "used_count": promocode.used_count,
            "is_active": promocode.is_active,
            "valid_from": promocode.valid_from.isoformat() if promocode.valid_from else None,
            "valid_until": promocode.valid_until.isoformat() if promocode.valid_until else None,
            "created_at": promocode.created_at.isoformat() if promocode.created_at else None,
            "updated_at": promocode.updated_at.isoformat() if promocode.updated_at else None
        }, message="Promocode updated successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to update promocode: {str(e)}"
        )


@router.delete("/{promocode_id}")
async def delete_promocode(
    promocode_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete promocode (Admin only)."""
    try:
        if current_user.role != "Admin":
            raise APIException(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Only admins can delete promocodes"
            )
        
        promocode_service = PromocodeService(db)
        success = await promocode_service.delete_promocode(promocode_id)
        
        if not success:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Promocode not found"
            )
        
        return Response.success(message="Promocode deleted successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to delete promocode: {str(e)}"
        )
