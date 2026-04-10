from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional

from core.db import get_db
from core.logging import get_structured_logger as get_logger
from services.catalog.wishlist import WishlistService
from schemas.catalog.wishlist import WishlistCreate, WishlistUpdate, WishlistResponse, WishlistItemCreate
from models.accounts.user import User
from core.dependencies import get_current_auth_user
from core.utils.response import Response
from core.exceptions import APIException

logger = get_logger(__name__)

router = APIRouter(prefix="/wishlists", tags=["Wishlists"])


@router.post("/")
async def create(
    payload: WishlistCreate,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new wishlist for current user."""
    try:
        wishlist_service = WishlistService(db)
        wishlist = await wishlist_service.create(current_user.id, payload)
        return Response.success(data=wishlist, message="Wishlist created successfully", code=status.HTTP_201_CREATED)
    except Exception as e:
        logger.error(f"Error creating wishlist for user {current_user.id}: {e}")
        raise APIException(status_code=500, message=f"Failed to create wishlist: {str(e)}")


@router.get("/{wishlist_id}")
async def get(
    wishlist_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific wishlist by ID."""
    try:
        wishlist_service = WishlistService(db)
        wishlist = await wishlist_service.get(wishlist_id, current_user.id)
        if not wishlist:
            raise APIException(status_code=404, message="Wishlist not found")
        return Response.success(data=wishlist)
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error fetching wishlist {wishlist_id}: {e}")
        raise APIException(status_code=500, message=f"Failed to fetch wishlist: {str(e)}")


@router.get("/")
async def list(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """List all wishlists for current user."""
    try:
        wishlist_service = WishlistService(db)
        result = await wishlist_service.list(current_user.id, page=page, limit=limit)
        if isinstance(result, dict):
            if "items" in result:
                pagination = {
                    "page": result.get("page", page),
                    "limit": result.get("limit", limit),
                    "total": result.get("total", 0),
                    "pages": result.get("pages", 1)
                }
                return Response.success(data=result.get("items", []), pagination=pagination)
            if "data" in result:
                pagination = {
                    "page": result.get("page", page),
                    "limit": result.get("limit", limit),
                    "total": result.get("total", 0),
                    "pages": result.get("pages", 1)
                }
                return Response.success(data=result.get("data", []), pagination=pagination)
        return Response.success(data=result)
    except Exception as e:
        logger.error(f"Error listing wishlists for user {current_user.id}: {e}")
        raise APIException(status_code=500, message=f"Failed to list wishlists: {str(e)}")


@router.patch("/{wishlist_id}")
async def patch(
    wishlist_id: UUID,
    payload: WishlistUpdate,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a wishlist."""
    try:
        wishlist_service = WishlistService(db)
        wishlist = await wishlist_service.update(wishlist_id, current_user.id, payload)
        if not wishlist:
            raise APIException(status_code=404, message="Wishlist not found")
        return Response.success(data=wishlist, message="Wishlist updated successfully")
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error updating wishlist {wishlist_id}: {e}")
        raise APIException(status_code=500, message=f"Failed to update wishlist: {str(e)}")


@router.delete("/{wishlist_id}")
async def delete(
    wishlist_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a wishlist."""
    try:
        wishlist_service = WishlistService(db)
        deleted = await wishlist_service.delete(wishlist_id, current_user.id)
        if not deleted:
            raise APIException(status_code=404, message="Wishlist not found")
        return Response.success(message="Wishlist deleted successfully")
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error deleting wishlist {wishlist_id}: {e}")
        raise APIException(status_code=500, message=f"Failed to delete wishlist: {str(e)}")