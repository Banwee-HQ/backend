from fastapi import APIRouter, Depends, status, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from core.db import get_db
from core.errors import APIException
from core.logging import get_logger
from services.cart import CartService
from models.user import User
from core.utils.response import Response
from schemas.cart import AddToCartRequest, ApplyPromocodeRequest, UpdateCartItemRequest
from core.dependencies import get_current_auth_user
from typing import Optional

logger = get_logger(__name__)

router = APIRouter(prefix="/cart", tags=["Cart"])


@router.get("/")
async def get_cart(
    request: Request,
    country: Optional[str] = None,
    province: Optional[str] = None,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get cart for authenticated user only.
    Requires authentication.
    """
    try:
        country_code = country or request.headers.get('X-Country-Code', 'US')
        province_code = province or request.headers.get('X-Province-Code')
        
        cart_service = CartService(db)
        
        # Authenticated user - use user_id
        cart = await cart_service.get_cart(
            user_id=current_user.id,
            session_id=None,
            country_code=country_code,
            province_code=province_code
        )
        
        return Response(success=True, data=cart)
    except Exception as e:
        logger.exception("Failed to retrieve cart")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve cart: {e}"
        )


@router.post("/add")
async def add_to_cart(
    request: AddToCartRequest,
    req: Request,
    country: Optional[str] = None,
    province: Optional[str] = None,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Add item to cart for authenticated user only.
    Requires authentication.
    """
    try:
        cart_service = CartService(db)
        
        # Authenticated user
        cart = await cart_service.add_to_cart(
            user_id=current_user.id,
            variant_id=request.variant_id,
            quantity=request.quantity,
            session_id=None
        )
        
        return Response(success=True, data=cart, message="Item added to cart")
    except HTTPException as e:
        raise APIException(status_code=e.status_code, message=e.detail)
    except Exception as e:
        logger.exception("Unexpected exception in add_to_cart")
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to add item to cart {str(e)}"
        )


@router.put("/items/{cart_item_id}")
async def update_cart_item(
    cart_item_id: UUID,
    request: UpdateCartItemRequest,
    req: Request,
    country: Optional[str] = None,
    province: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update cart item quantity by cart_item_id
    
    The cart_item_id is the unique ID assigned to each item when added to cart,
    not the variant_id or product_id.
    """
    try:
        logger.info(f"Update cart item endpoint hit: cart_item_id={cart_item_id}, quantity={request.quantity}, user_id={current_user.id if current_user else None}")
        
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Get location from query params or headers
        country_code = country or req.headers.get('X-Country-Code', 'US')
        province_code = province or req.headers.get('X-Province-Code')
        
        logger.info(f"Location: country={country_code}, province={province_code}")
        
        cart_service = CartService(db)
        
        # First check if user has a cart
        try:
            cart_data = await cart_service.get_cart(user_id=current_user.id)
            if not cart_data or not cart_data.get('items'):
                logger.warning(f"User {current_user.id} has no cart or empty cart")
                raise HTTPException(status_code=404, detail="Cart is empty or expired. Please add items to your cart.")
        except Exception as e:
            logger.error(f"Failed to get cart for user {current_user.id}: {e}")
            raise HTTPException(status_code=404, detail="Cart not found or expired. Please refresh and try again.")
        
        # Check if the specific item exists in cart
        cart_items = cart_data.get('items', [])
        item_exists = any(str(item['id']) == str(cart_item_id) for item in cart_items)
        if not item_exists:
            logger.warning(f"Cart item {cart_item_id} not found in user {current_user.id}'s cart")
            available_items = [item['id'] for item in cart_items]
            logger.info(f"Available cart items: {available_items}")
            raise HTTPException(status_code=404, detail="Cart item not found. It may have been removed or your cart may have expired.")
        
        # Use the update_cart_item_quantity method which handles cart_item_id
        logger.info(f"Calling update_cart_item_quantity...")
        result = await cart_service.update_cart_item_quantity(
            user_id=current_user.id,
            cart_item_id=cart_item_id,
            quantity=request.quantity
        )
        logger.info(f"Update result: {result}")
        
        # Re-fetch cart with location to recalculate tax
        logger.info(f"Re-fetching cart with location...")
        cart = await cart_service.get_cart(
            user_id=current_user.id,
            country_code=country_code,
            province_code=province_code
        )
        logger.info(f"Cart fetched successfully")
        
        return Response(success=True, data=cart, message="Cart item quantity updated")
    except HTTPException as e:
        logger.error(f"HTTPException in update_cart_item: {e.status_code} - {e.detail}")
        raise APIException(status_code=e.status_code, message=e.detail)
    except Exception as e:
        logger.exception("Error updating cart item")
        raise APIException(status_code=status.HTTP_400_BAD_REQUEST,
                           message=f"Failed to update cart item quantity: {e}")


@router.delete("/items/{cart_item_id}")
async def remove_from_cart(
    cart_item_id: UUID,
    req: Request,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove item from cart by cart_item_id"""
    try:
        cart_service = CartService(db)
        
        cart = await cart_service.remove_from_cart_by_item_id(
            user_id=current_user.id,
            cart_item_id=cart_item_id
        )
        
        return Response(success=True, data=cart, message="Item removed from cart")
    except HTTPException as e:
        raise APIException(status_code=e.status_code, message=e.detail)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to remove item from cart: {e}"
        )


@router.post("/promocode")
async def apply_promocode(
    request: ApplyPromocodeRequest,
    req: Request,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        cart_service = CartService(db)
        result = await cart_service.apply_promocode(
            user_id=current_user.id,
            code=request.code,
            session_id=None
        )
        return Response(success=True, data=result)
    except Exception as e:
        raise APIException(status_code=status.HTTP_400_BAD_REQUEST,
                           message=f"Failed to apply promocode: {e}")


@router.delete("/promocode")
async def remove_promocode(
    request: Request,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        cart_service = CartService(db)
        result = await cart_service.remove_promocode(
            user_id=current_user.id,
            session_id=None
        )
        return Response(success=True, data=result)
    except Exception:
        raise APIException(status_code=status.HTTP_400_BAD_REQUEST,
                           message="Failed to remove promocode")


@router.get("/count")
async def get_cart_item_count(
    request: Request,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        cart_service = CartService(db)
        count = await cart_service.get_cart_item_count(
            user_id=current_user.id,
            session_id=None
        )
        return Response(success=True, data=count)
    except Exception:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message="Failed to get cart count")


@router.post("/validate")
async def validate_cart(
    request: Request,
    country: Optional[str] = None,
    province: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Comprehensive cart validation - should be called before checkout
    Validates availability, stock, prices, and product status
    """
    try:
        cart_service = CartService(db)
        
        if not current_user:
            raise APIException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                message="Authentication required for cart validation"
            )
        
        # Get location from query params or headers
        country_code = country or request.headers.get('X-Country-Code', 'US')
        province_code = province or request.headers.get('X-Province-Code')
        
        result = await cart_service.validate_cart(
            user_id=current_user.id,
            country_code=country_code,
            province_code=province_code
        )
        
        # Determine response status based on validation results
        if result.get("valid", False) and result.get("can_checkout", False):
            return Response(
                success=True, 
                data=result, 
                message="Cart validation successful - ready for checkout"
            )
        elif result.get("issues"):
            # Cart has issues but may be recoverable
            error_count = len([issue for issue in result["issues"] if issue.get("severity") == "error"])
            warning_count = len([issue for issue in result["issues"] if issue.get("severity") == "warning"])
            
            if error_count > 0:
                return Response(
                    success=False,
                    data=result,
                    message=f"Cart validation failed with {error_count} error(s) and {warning_count} warning(s). Please review your cart."
                )
            else:
                return Response(
                    success=True,
                    data=result,
                    message=f"Cart validation completed with {warning_count} warning(s). You can proceed to checkout."
                )
        else:
            return Response(
                success=False,
                data=result,
                message="Cart validation failed"
            )
            
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Cart validation error: {str(e)}"
        )


@router.post("/shipping-options")
async def get_shipping_options(
    address: dict,
    request: Request,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        cart_service = CartService(db)
        result = await cart_service.get_shipping_options(
            user_id=current_user.id,
            address=address,
            session_id=None
        )
        return Response(success=True, data=result)
    except Exception as e:
        raise APIException(status_code=status.HTTP_400_BAD_REQUEST,
                           message=f"Failed to get shipping options: {e}")


@router.post("/calculate")
async def calculate_totals(
    data: dict,
    request: Request,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        cart_service = CartService(db)
        result = await cart_service.calculate_totals(
            user_id=current_user.id,
            data=data,
            session_id=None
        )
        return Response(success=True, data=result)
    except Exception as e:
        logger.error(f"Failed to calculate totals: {str(e)}", exc_info=True)
        raise APIException(status_code=status.HTTP_400_BAD_REQUEST,
                           message=f"Failed to calculate totals: {str(e)}")


@router.post("/clear")
async def clear_cart(
    request: Request,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Clear all items from the cart"""
    try:
        cart_service = CartService(db)
        result = await cart_service.clear_cart(
            user_id=current_user.id,
            session_id=None
        )
        return Response(success=True, data=result, message="Cart cleared successfully")
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to clear cart: {str(e)}"
        )


@router.get("/checkout-summary")
async def get_checkout_summary(
    request: Request,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        cart_service = CartService(db)
        result = await cart_service.get_checkout_summary(
            user_id=current_user.id,
            session_id=None
        )
        return Response(success=True, data=result)
    except Exception:
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                           message="Failed to get checkout summary")
