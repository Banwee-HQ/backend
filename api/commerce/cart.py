from fastapi import APIRouter, Depends, status, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from core.db import get_db
from core.exceptions import APIException
from core.logging import get_structured_logger as get_logger
from services.commerce.cart import CartService
from models.accounts.user import User
from core.utils.response import Response
from schemas.commerce.cart import Add, UpdateItem
from core.dependencies import get_current_auth_user
from typing import Optional

logger = get_logger(__name__)

router = APIRouter(prefix="/cart", tags=["Cart"])


# ==========================================================
# CART - 5 Standard APIs (operating on cart items)
# ==========================================================
@router.post("/")
async def create(
    request: Add,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Add item to cart (create cart item)."""
    try:
        cart_service = CartService(db)
        cart = await cart_service.add_to_cart(
            user_id=current_user.id,
            variant_id=request.variant_id,
            quantity=request.quantity
        )
        return Response.success(data=cart, message="Item added to cart")
    except HTTPException as e:
        raise APIException(status_code=e.status_code, message=e.detail)
    except Exception as e:
        raise APIException(status_code=400, message=f"Failed to add item to cart: {str(e)}")


@router.post("/add/")
async def add_alias(
    payload: Add,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Legacy alias for adding item to cart at /cart/add"""
    return await create(payload, current_user=current_user, db=db)


@router.get("/")
async def get(
    request: Request,
    country: Optional[str] = None,
    province: Optional[str] = None,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's cart (includes items list)."""
    try:
        country_code = country or request.headers.get('X-Country-Code', 'US')
        province_code = province or request.headers.get('X-Province-Code')
        cart_service = CartService(db)
        cart = await cart_service.get_cart(
            user_id=current_user.id,
            country_code=country_code,
            province_code=province_code
        )
        return Response.success(data=cart)
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to retrieve cart: {e}")


@router.patch("/{item_id}/")
async def patch(
    item_id: UUID,
    request: UpdateItem,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Update cart item quantity (partial update)."""
    try:
        cart_service = CartService(db)
        result = await cart_service.update_item(
            user_id=current_user.id,
            cart_item_id=item_id,
            quantity=request.quantity
        )
        cart = await cart_service.get_cart(user_id=current_user.id)
        return Response.success(data=cart, message="Cart item updated")
    except HTTPException as e:
        raise APIException(status_code=e.status_code, message=e.detail)
    except Exception as e:
        raise APIException(status_code=400, message=f"Failed to update cart item: {e}")


@router.patch("/items/{item_id}/")
async def patch_item(item_id: UUID, request: UpdateItem, current_user: User = Depends(get_current_auth_user), db: AsyncSession = Depends(get_db)):
    """Compatibility: support PATCH /cart/items/{id}"""
    return await patch(item_id=item_id, request=request, current_user=current_user, db=db)


@router.delete("/{item_id}/")
async def delete(
    item_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove item from cart."""
    try:
        cart_service = CartService(db)
        cart = await cart_service.remove_item(
            user_id=current_user.id,
            cart_item_id=item_id
        )
        return Response.success(data=cart, message="Item removed from cart")
    except HTTPException as e:
        raise APIException(status_code=e.status_code, message=e.detail)
    except Exception as e:
        raise APIException(status_code=400, message=f"Failed to remove item: {e}")


@router.delete("/items/{item_id}/")
async def delete_item(item_id: UUID, current_user: User = Depends(get_current_auth_user), db: AsyncSession = Depends(get_db)):
    """Compatibility: DELETE /cart/items/{id}"""
    return await delete(item_id=item_id, current_user=current_user, db=db)


@router.get("/count/")
async def count(
    request: Request,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        cart_service = CartService(db)
        count = await cart_service.item_count(
            user_id=current_user.id
        )
        return Response.success(data=count)
    except Exception:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message="Failed to get cart count")


@router.post("/validate/")
async def validate(
    request: Request,
    country: Optional[str] = None,
    province: Optional[str] = None,
    current_user: User = Depends(get_current_auth_user),
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
        
        # Convert result to dict for response
        result_dict = {
            "valid": result.get('valid', False),
            "can_checkout": result.get('can_checkout', False),
            "issues": result.get('issues', []),
            "summary": result.get('summary', {}),
        }

        if result.get('valid', False) and result.get('can_checkout', False):
            return Response.success(data=result_dict, message="Cart validation successful - ready for checkout")
        elif result.get('issues'):
            error_count = len([i for i in result.get('issues', []) if i.get("severity") == "error"])
            warning_count = len([i for i in result.get('issues', []) if i.get("severity") == "warning"])
            if error_count > 0:
                errors = [i for i in result_dict["issues"] if i.get("severity") == "error"]
                return Response.error(data=result_dict, message=f"Cart validation failed with {error_count} error(s) and {warning_count} warning(s).", errors=errors)
            else:
                return Response.success(data=result_dict,
                    message=f"Cart validation completed with {warning_count} warning(s). You can proceed to checkout."
                )
        else:
            return Response.error(data=result_dict, message="Cart validation failed")
            
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Cart validation error: {str(e)}"
        )


@router.post("/calculate/")
async def calculate(
    data: dict,
    request: Request,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        cart_service = CartService(db)
        result = await cart_service.calc_totals(
            user_id=current_user.id,
            data=data
        )
        return Response.success(data=result)
    except Exception as e:
        logger.error(f"Failed to calculate totals: {str(e)}", exc_info=True)
        raise APIException(status_code=status.HTTP_400_BAD_REQUEST,
                           message=f"Failed to calculate totals: {str(e)}")


@router.post("/clear/")
async def clear(
    request: Request,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Clear all items from the cart"""
    try:
        cart_service = CartService(db)
        result = await cart_service.clear_cart(
            user_id=current_user.id
        )
        return Response.success(data=result, message="Cart cleared successfully")
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to clear cart: {str(e)}"
        )


@router.get("/checkout-summary/")
async def summary(
    request: Request,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        cart_service = CartService(db)
        result = await cart_service.checkout_summary(
            user_id=current_user.id
        )
        return Response.success(data=result)
    except Exception:
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                           message="Failed to get checkout summary")
