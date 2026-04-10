"""
Standalone address endpoints at /v1/addresses
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List

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


@router.post("/", response_model=Response[AddressResponse])
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


@router.get("/{address_id}", response_model=Response[AddressResponse])
async def get_address(
    address_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific address for current user."""
    try:
        service = AddressService(db)
        address = await service.get(address_id)
        if not address or address.user_id != current_user.id:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND, message="Address not found")
        return Response.success(data=address)
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to get address: {str(e)}"
        )


@router.get("/", response_model=Response[List[AddressResponse]])
async def list_addresses(
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """List all addresses for current user."""
    try:
        service = AddressService(db)
        addresses = await service.list(current_user.id)
        return Response.success(data=addresses)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to list addresses: {str(e)}"
        )


@router.patch("/{address_id}", response_model=Response[AddressResponse])
async def patch_address(
    address_id: UUID,
    payload: AddressUpdate,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Partially update address for current user."""
    try:
        service = AddressService(db)
        address = await service.get(address_id)
        if not address or address.user_id != current_user.id:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND, message="Address not found")
        updated = await service.update(address_id, current_user.id, **payload.model_dump(exclude_unset=True, exclude_none=True))
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
        address = await service.get(address_id)
        if not address or address.user_id != current_user.id:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND, message="Address not found")
        deleted = await service.delete(address_id, current_user.id)
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
