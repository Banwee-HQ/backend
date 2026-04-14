from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from uuid import UUID
from core.db import get_db
from core.utils.response import Response
from core.exceptions import APIException
from schemas.commerce.promos import Create, Update, ValidateRequest, ValidateResponse
from services.commerce.promocode import PromocodeService
from services.commerce.promocode_scheduler import PromoCodeScheduler
from models.accounts.user import User
from core.dependencies import get_current_auth_user, require_admin
from fastapi.security import OAuth2PasswordBearer
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)

router = APIRouter(prefix="/promocodes", tags=["promocodes"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


@router.get("/")
async def list(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    is_active: Optional[bool] = Query(None),
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all promocodes. Returns only active promocodes for regular users, all for admins."""
    try:
        from models.accounts.user import UserRole
        is_admin = current_user.role in [UserRole.ADMIN, UserRole.MANAGER]
        
        promocode_service = PromocodeService(db)
        # Regular users only see active promocodes
        filter_active = True if not is_admin else is_active
        promocodes, total = await promocode_service.list(
            page=page, limit=limit, is_active=filter_active
        )
        promocodes_serialized = [
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
            for p in promocodes
        ]

        return Response.success(data=promocodes_serialized, pagination={
            "page": page,
            "limit": limit,
            "total": total,
            "pages": max(1, (total + limit - 1) // limit)
        })
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch promocodes: {str(e)}"
        )


@router.post("/validate/")
async def validate(
    request: ValidateRequest,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Validate a promocode."""
    try:
        promocode_service = PromocodeService(db)
        is_valid, error_message, promocode = await promocode_service.validate(request.code)
        
        if is_valid and promocode:
            return Response.success(data={
                "valid": True,
                "code": promocode.code,
                "discount_type": promocode.discount_type,
                "value": promocode.value,
                "minimum_order_amount": promocode.minimum_order_amount,
                "maximum_discount_amount": promocode.maximum_discount_amount,
                "message": "Promocode is valid"
            })
        else:
            return Response.success(data={
                "valid": False,
                "code": request.code,
                "message": error_message or "Invalid promocode"
            }, status_code=status.HTTP_200_OK)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to validate promocode: {str(e)}"
        )


@router.get("/{promocode_id}/")
async def get(
    promocode_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get promocode by ID."""
    try:
        from models.accounts.user import UserRole
        is_admin = current_user.role in [UserRole.ADMIN, UserRole.MANAGER]
        
        promocode_service = PromocodeService(db)
        promocode = await promocode_service.get(promocode_id)
        
        # Regular users can only view active promocodes
        if not is_admin and promocode and not promocode.is_active:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Promocode not found"
            )
        
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
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch promocode: {str(e)}"
        )


@router.post("/")
async def create(
    promocode_data: Create,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create new promocode (Admin only)."""
    try:
        promocode_service = PromocodeService(db)
        promocode = await promocode_service.create(promocode_data)
        
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
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to create promocode: {str(e)}"
        )


@router.patch("/{promocode_id}/")
async def update(
    promocode_id: UUID,
    promocode_data: Update,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update promocode (Admin only)."""
    try:
        promocode_service = PromocodeService(db)
        promocode = await promocode_service.update(promocode_id, promocode_data)
        
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
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to update promocode: {str(e)}"
        )


@router.delete("/{promocode_id}/")
async def delete(
    promocode_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete promocode (Admin only)."""
    try:
        promocode_service = PromocodeService(db)
        success = await promocode_service.delete(promocode_id)
        
        if not success:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Promocode not found"
            )
        
        return Response.success(message="Promocode deleted successfully")
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to delete promocode: {str(e)}"
        )


@router.post("/trigger-cleanup/")
async def trigger_cleanup(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Manually trigger promocode status cleanup (admin only).
    
    This endpoint:
    - Activates promocodes that have reached their valid_from date
    - Deactivates expired promocodes (past valid_until)
    - Deactivates promocodes that reached usage limit
    - Deactivates promocodes not yet valid
    """
    try:
        scheduler = PromoCodeScheduler(db)
        result = await scheduler.update_promocode_statuses()
        if result.get("success"):
            return Response.success(
                data=result,
                message=f"Promocode cleanup completed: {result.get('activated_count', 0)} activated, {result.get('deactivated_count', 0)} deactivated"
            )
        else:
            raise APIException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message=f"Promocode cleanup failed: {result.get('error', 'Unknown error')}"
            )
    except Exception as e:
        logger.error(f"Error triggering promocode cleanup: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to trigger promocode cleanup: {str(e)}"
        )
