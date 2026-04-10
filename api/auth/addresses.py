"""
Standalone address endpoints at /v1/addresses
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from core.db import get_db
from core.utils.response import Response
from core.exceptions import APIException
from core.dependencies import get_current_auth_user
from models.accounts.user import User
from schemas.accounts.user import AddressCreate, AddressUpdate, AddressResponse
from services.accounts.user import AddressService
from core.logging import get_structured_logger as get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/addresses", tags=["Addresses"])


@router.post("/")
async def create_address(
    payload: AddressCreate,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Create address for current user."""
    try:
        service = AddressService(db)
        address = await service.create(user_id=current_user.id, **payload.model_dump(exclude_none=True))
        return Response.success(data=address, message="Address created successfully")
    except Exception as e:
        logger.error(f"Error creating address: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to create address: {str(e)}"
        )


@router.put("/{address_id}")
async def update_address(
    address_id: UUID,
    payload: AddressUpdate,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Update address for current user."""
    try:
        service = AddressService(db)
        updated = await service.update(address_id, current_user.id, **payload.model_dump(exclude_unset=True, exclude_none=True))
        if not updated:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND, message="Address not found")
        return Response.success(data=updated, message="Address updated successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to update address: {str(e)}"
        )


@router.delete("/{address_id}")
async def delete_address(
    address_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete address for current user."""
    try:
        service = AddressService(db)
        address = await service.get_address_by_id(address_id)
        if not address or address.user_id != current_user.id:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND, message="Address not found")
        deleted = await service.delete(address_id)
        if not deleted:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND, message="Address not found")
        return Response.success(message="Address deleted successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to delete address: {str(e)}"
        )


@router.patch("/{address_id}/default")
async def set_default_address(
    address_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Set address as default for current user."""
    try:
        service = AddressService(db)
        address = await service.get_address_by_id(address_id)
        if not address or address.user_id != current_user.id:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND, message="Address not found")
        updated = await service.update(address_id, current_user.id, is_default=True)
        return Response.success(data=updated, message="Default address set successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to set default address: {str(e)}"
        )
