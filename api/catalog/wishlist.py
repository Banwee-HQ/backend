from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from core.db import get_db
from core.logging import get_logger
from services.wishlist import WishlistService
from schemas.wishlist import WishlistCreate, WishlistUpdate, WishlistResponse, WishlistItemCreate, WishlistItemResponse
from models.user import User
from core.dependencies import get_current_auth_user
from core.utils.response import Response
from core.errors import APIException

logger = get_logger(__name__)

# Simple wishlist router for easier API access
router = APIRouter(prefix="/wishlist", tags=["Wishlists"])

@router.get("/")
async def get_current_user_wishlist(
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's default wishlist"""
    try:
        wishlist_service = WishlistService(db)
        wishlists = await wishlist_service.get_wishlists(current_user.id)
        
        # Get default wishlist or first one
        default_wishlist = next((w for w in wishlists if w.is_default), None)
        if not default_wishlist and wishlists:
            default_wishlist = wishlists[0]
        
        if not default_wishlist:
            # Create default wishlist if none exists
            payload = WishlistCreate(name="My Wishlist", is_default=True)
            default_wishlist = await wishlist_service.create_wishlist(current_user.id, payload)
        
        # Return simple data
        wishlist_data = {
            "id": str(default_wishlist.id),
            "name": default_wishlist.name or "My Wishlist",
            "is_default": default_wishlist.is_default,
            "item_count": len(default_wishlist.items) if default_wishlist.items else 0,
            "items": []
        }
        
        return Response.success(data=wishlist_data)
    except Exception as e:
        logger.error(f"Error retrieving wishlist for user {current_user.id}: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve wishlist: {str(e)}"
        )


@router.post("/add")
async def add_to_wishlist(
    product_data: dict,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Add product to current user's default wishlist"""
    try:
        product_id = product_data.get("product_id")
        variant_id = product_data.get("variant_id")
        
        if not product_id:
            raise APIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="product_id is required"
            )
        
        # If variant_id is not provided, get the first available variant for the product
        if not variant_id:
            from models.product import ProductVariant
            from sqlalchemy import select
            
            variant_query = select(ProductVariant).where(
                ProductVariant.product_id == product_id,
                ProductVariant.is_active == True
            ).limit(1)
            
            result = await db.execute(variant_query)
            variant = result.scalar_one_or_none()
            
            if not variant:
                raise APIException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    message="No active variants found for this product"
                )
            
            variant_id = variant.id
        
        wishlist_service = WishlistService(db)
        
        # Get or create default wishlist
        wishlists = await wishlist_service.get_wishlists(current_user.id)
        default_wishlist = next((w for w in wishlists if w.is_default), None)
        
        if not default_wishlist:
            payload = WishlistCreate(name="My Wishlist", is_default=True)
            default_wishlist = await wishlist_service.create_wishlist(current_user.id, payload)
        
        # Add item to wishlist
        item_payload = WishlistItemCreate(
            product_id=product_id,
            variant_id=variant_id,
            quantity=product_data.get("quantity", 1)
        )
        
        item = await wishlist_service.add_item_to_wishlist(default_wishlist.id, item_payload)
        
        return Response.success(
            data={
                "wishlist_id": str(default_wishlist.id),
                "item_id": str(item.id),
                "product_id": str(item.product_id),
                "variant_id": str(item.variant_id)
            },
            message="Product added to wishlist successfully"
        )
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error adding to wishlist for user {current_user.id}: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to add to wishlist: {str(e)}"
        )


@router.delete("/items/{product_id}")
async def remove_from_wishlist(
    product_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove product from current user's default wishlist"""
    try:
        wishlist_service = WishlistService(db)
        
        # Get default wishlist
        wishlists = await wishlist_service.get_wishlists(current_user.id)
        default_wishlist = next((w for w in wishlists if w.is_default), None)
        
        if not default_wishlist:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Wishlist not found"
            )
        
        # Remove item from wishlist
        success = await wishlist_service.remove_item_from_wishlist(default_wishlist.id, product_id)
        
        if not success:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Product not found in wishlist"
            )
        
        return Response.success(
            data={"product_id": str(product_id)},
            message="Product removed from wishlist successfully"
        )
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error removing from wishlist for user {current_user.id}: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to remove from wishlist: {str(e)}"
        )