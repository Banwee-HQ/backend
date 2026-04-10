from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, status, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from uuid import UUID
from typing import List
from core.db import get_db,logger
from core.utils.response import Response
from core.exceptions import APIException
from schemas.commerce.subscriptions import (
    CreateSubscription, 
    UpdateSubscription, 
    SubscriptionResponse,
    SubscriptionCostCalculationRequest,
    SubscriptionAddProducts,
    SubscriptionRemoveProducts,
    SubscriptionUpdateQuantity,
    SubscriptionQuantityChange,
    DiscountApplicationRequest
)
from services.commerce.subscriptions import SubscriptionService
from services.commerce.subscriptions_scheduler import SubscriptionScheduler
from models.accounts.user import User
from models.catalog.product import Product, ProductVariant, ProductImage
from models.commerce.subscriptions import Subscription
from services.accounts.auth import AuthService


from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])

async def get_current_auth_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    auth_service = AuthService(db)
    return await auth_service.current_user(token)


@router.post("/trigger-order-processing")
async def trigger_subscription_order_processing(
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Manually trigger subscription order processing (admin only)."""
    from models.accounts.user import UserRole
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise APIException(status_code=status.HTTP_403_FORBIDDEN, message="Admin access required")
    try:
        scheduler = SubscriptionScheduler(db)
        result = await scheduler.process_due_subscriptions()
        return Response.success(data=result, message="Subscription order processing triggered successfully")
    except Exception as e:
        logger.error(f"Error triggering subscription order processing: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to trigger order processing: {str(e)}"
        )


@router.post("/trigger-notifications")
async def trigger_subscription_notifications(
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
    ):
    """Manually trigger subscription order notifications (admin only)."""
    from models.accounts.user import UserRole
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise APIException(status_code=status.HTTP_403_FORBIDDEN, message="Admin access required")
    try:
        return Response.success(message="Subscription order notifications triggered successfully")
    except Exception as e:
        logger.error(f"Error triggering subscription notifications: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to trigger notifications: {str(e)}"
        )


@router.get("/plans")
async def get_subscription_plans(
    db: AsyncSession = Depends(get_db)
):
    """Get available subscription plans (public endpoint)."""
    try:
        # Return subscription plan information
        # This is a simplified version - in a real app, you might have a SubscriptionPlan model
        plans = [
            {
                "id": "monthly",
                "name": "Monthly Plan",
                "description": "Monthly subscription with flexible delivery",
                "billing_cycle": "monthly",
                "features": [
                    "Flexible delivery scheduling",
                    "Skip or pause anytime",
                    "10% off all orders",
                    "Free shipping on orders over $50"
                ]
            },
            {
                "id": "quarterly",
                "name": "Quarterly Plan",
                "description": "Quarterly subscription with best value",
                "billing_cycle": "quarterly",
                "features": [
                    "Save 15% compared to monthly",
                    "Priority delivery scheduling",
                    "15% off all orders",
                    "Free shipping on all orders",
                    "Exclusive access to new products"
                ]
            },
            {
                "id": "yearly",
                "name": "Yearly Plan",
                "description": "Annual subscription with maximum savings",
                "billing_cycle": "yearly",
                "features": [
                    "Save 25% compared to monthly",
                    "VIP delivery scheduling",
                    "20% off all orders",
                    "Free express shipping",
                    "Exclusive access to new products",
                    "Dedicated customer support"
                ]
            }
        ]
        
        return Response.success(data=plans, message="Subscription plans retrieved successfully")
    except Exception as e:
        logger.error(f"Error fetching subscription plans: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch subscription plans: {str(e)}"
        )


@router.post("/calculate-cost")
async def calculate_subscription_cost(
    cost_request: SubscriptionCostCalculationRequest,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
    ):
    """Calculate subscription cost with VAT before creating subscription."""
    try:
        subscription_service = SubscriptionService(db)
        
        # Get variants
        variant_result = await db.execute(
            select(ProductVariant).where(ProductVariant.id.in_(cost_request.variant_ids))
        )
        variants = variant_result.scalars().all()
        
        if len(variants) != len(cost_request.variant_ids):
            raise APIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Some product variants not found"
            )
        
        # Get customer address for tax calculation
        customer_address = None
        if cost_request.delivery_address_id:
            from models.accounts.user import Address
            address_result = await db.execute(
                select(Address).where(
                    and_(Address.id == cost_request.delivery_address_id, Address.user_id == current_user.id)
                )
            )
            address = address_result.scalar_one_or_none()
            if address:
                customer_address = {
                    "street": address.street,
                    "city": address.city,
                    "state": address.state,
                    "country": address.country,
                    "post_code": address.post_code
                }
        
        # Calculate cost
        cost_breakdown = await subscription_service._calc_cost(
            variants=variants,
            delivery_type=cost_request.delivery_type,
            customer_address=customer_address,
            currency=cost_request.currency,
            user_id=current_user.id
        )
        
        return Response.success(
            data={
                "cost_breakdown": cost_breakdown,
                "estimated_total": cost_breakdown.get("total", cost_breakdown.get("total_amount", 0)),
                "currency": cost_request.currency,
                "calculation_timestamp": datetime.now(timezone.utc)
            },
            message="Subscription cost calculated successfully"
        )
        
    except Exception as e:
        logger.error(f"Error calculating subscription cost: {e}")
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to calculate subscription cost: {str(e)}"
        )


@router.post("/")
async def create_subscription(
    subscription_data: CreateSubscription,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
    ):
    """Create a new subscription with product quantities and VAT calculation."""
    try:
        subscription_service = SubscriptionService(db)
        # Extract data from request
        product_variant_ids = subscription_data.variant_ids or []
        variant_quantities = subscription_data.variant_quantities

        # If no variant_ids provided (e.g. plan_id based request), return 400
        if not product_variant_ids:
            raise APIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="variant_ids is required to create a subscription"
            )

        # Create subscription with quantities
        subscription = await subscription_service.create(
            user_id=current_user.id,
            name=subscription_data.name,
            product_variant_ids=product_variant_ids,
            variant_quantities=variant_quantities,
            delivery_type=subscription_data.delivery_type,
            delivery_address_id=subscription_data.delivery_address_id,
            payment_method_id=subscription_data.payment_method_id,
            currency=subscription_data.currency
        )
        return Response.success(
            data=subscription.to_dict(include_products=True),
            message="Subscription created successfully! Orders will be placed automatically based on your billing cycle."
        )
    except APIException as e:
        raise e
    except Exception as e:
        logger.error(f"Error creating subscription: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to create subscription: {str(e)}"
        )
@router.get("/")
async def get_subscriptions(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
    ):
    """Get user's subscriptions."""
    try:
        subscription_service = SubscriptionService(db)
        subscriptions, total = await subscription_service.list(
            user_id=current_user.id, page=page, limit=limit
        )
        serialized = [sub.to_dict(include_products=True) for sub in subscriptions]
        return Response.success(data=serialized, pagination={
            "page": page,
            "limit": limit,
            "total": total,
            "pages": max(1, (total + limit - 1) // limit)
        })
    except APIException:
        raise APIException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message="Failed to get subscriptions"
    )
    except Exception as e:
        raise APIException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message=f"Failed to get subscriptions: {str(e)}"
    )
@router.post("/{subscription_id}/products")
async def add_products_to_subscription(
    subscription_id: UUID,
    request: SubscriptionAddProducts,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
    ):
    """Add products to an existing subscription."""
    try:
        subscription_service = SubscriptionService(db)
        subscription = await subscription_service.add_products(
        subscription_id, request.variant_ids, current_user.id
        )
        # Load the products relationship properly for the response
        await db.refresh(subscription)
        subscription_result = await db.execute(
        select(Subscription).where(Subscription.id == subscription_id)
        .options(selectinload(Subscription.products).selectinload(ProductVariant.product))
        )
        subscription_with_products = subscription_result.scalar_one_or_none()
        return Response.success(
            data=subscription_with_products.to_dict(include_products=True) if subscription_with_products else subscription.to_dict(), 
            message="Products added to subscription successfully"
        )
    except APIException as e:
        print(e,'====error')
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to add products to subscription: {str(e)}"
        )
    except Exception as e:
        print(e,'====error')
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to add products to subscription: {str(e)}"
        )
@router.delete("/{subscription_id}/products")
async def remove_products_from_subscription(
    subscription_id: UUID,
    request: SubscriptionRemoveProducts,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
    ):
    """Remove products from an existing subscription."""
    try:
        subscription_service = SubscriptionService(db)
        subscription = await subscription_service.remove_products(
        subscription_id, request.variant_ids, current_user.id
        )
        # Load the products relationship properly for the response
        await db.refresh(subscription)
        subscription_result = await db.execute(
        select(Subscription).where(Subscription.id == subscription_id)
        .options(selectinload(Subscription.products).selectinload(ProductVariant.product))
        )
        subscription_with_products = subscription_result.scalar_one_or_none()
        return Response.success(
            data=subscription_with_products.to_dict(include_products=True) if subscription_with_products else subscription.to_dict(), 
            message="Products removed from subscription successfully"
        )
    except APIException:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to remove products from subscription"
        )
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to remove products from subscription: {str(e)}"
        )
@router.patch("/{subscription_id}/products/quantity")
async def update_variant_quantity(
    subscription_id: UUID,
    request: SubscriptionUpdateQuantity,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
    ):
    """Update the quantity of a specific variant in a subscription."""
    try:
        subscription_service = SubscriptionService(db)
        subscription = await subscription_service.set_quantity(
            subscription_id, request.variant_id, request.quantity, current_user.id
            )
        return Response.success(
            data=subscription.to_dict(include_products=True), 
            message=f"Variant quantity updated to {request.quantity} successfully"
        )
    except APIException:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to update variant quantity"
        )
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to update variant quantity: {str(e)}"
        )
@router.patch("/{subscription_id}/products/quantity")
async def change_variant_quantity(
    subscription_id: UUID,
    request: SubscriptionQuantityChange,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
    ):
    """Increment or decrement the quantity of a specific variant in a subscription."""
    try:
        subscription_service = SubscriptionService(db)
        subscription = await subscription_service.adjust_quantity(
            subscription_id, request.variant_id, request.change, current_user.id
        )
        action = "increased" if request.change > 0 else "decreased"
        return Response.success(
            data=subscription.to_dict(include_products=True), 
            message=f"Variant quantity {action} by {abs(request.change)} successfully"
        )
    except APIException:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to change variant quantity"
        )
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to change variant quantity: {str(e)}"
        )
@router.get("/{subscription_id}/products/quantities")
async def get_subscription_variant_quantities(
    subscription_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
    ):
    """Get the quantities of all variants in a subscription."""
    try:
        subscription_service = SubscriptionService(db)
        quantities = await subscription_service.get_quantities(
            subscription_id, current_user.id
            )
        return Response.success(
            data={"variant_quantities": quantities}, 
            message="Variant quantities retrieved successfully"
        )
    except APIException:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to get variant quantities"
        )
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to get variant quantities: {str(e)}"
        )
@router.patch("/{subscription_id}/auto-renew")
async def toggle_auto_renew(
    subscription_id: UUID,
    auto_renew: bool,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
    ):
    """Simple toggle for auto-renew setting."""
    try:
        subscription_service = SubscriptionService(db)
        # Get the subscription
        subscription = await subscription_service.get(subscription_id, current_user.id)
        if not subscription:
            raise APIException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Subscription not found"
            )
        # Update auto_renew
        subscription.auto_renew = auto_renew
        await db.commit()
        await db.refresh(subscription)
        return Response.success(
            data={
                "id": str(subscription.id),
                "auto_renew": subscription.auto_renew,
                "status": subscription.status,
                "next_billing_date": subscription.next_billing_date.isoformat() if subscription.next_billing_date else None
                },
                message=f"Auto-renew {'enabled' if auto_renew else 'disabled'}"
            )
    except APIException as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to update auto-renew: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error updating auto-renew: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to update auto-renew setting"
        )
@router.get("/{subscription_id}")
async def get_subscription(
    subscription_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
    ):
    """Get a specific subscription."""
    try:
        subscription_service = SubscriptionService(db)
        subscription = await subscription_service.get(subscription_id, current_user.id)
        if not subscription:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Subscription not found"
            )
        return Response.success(data=subscription.to_dict(include_products=True))
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch subscription: {str(e)}"
        )
@router.patch("/{subscription_id}")
async def update_subscription(
    subscription_id: UUID,
    subscription_data: UpdateSubscription,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a subscription."""
    try:
        subscription_service = SubscriptionService(db)
        # Extract product_variant_ids and other data
        product_variant_ids = getattr(subscription_data, 'variant_ids', None) or getattr(subscription_data, 'product_variant_ids', None)
        # Pass data directly to the service method
        subscription = await subscription_service.update(
            subscription_id=subscription_id,
            user_id=current_user.id,
            name=subscription_data.name if hasattr(subscription_data, 'name') else None,
            product_variant_ids=product_variant_ids,
            # Pass other updateable fields from subscription_data
            delivery_type=subscription_data.delivery_type if hasattr(subscription_data, 'delivery_type') else None,
            delivery_address_id=subscription_data.delivery_address_id if hasattr(subscription_data, 'delivery_address_id') else None,
            auto_renew=subscription_data.auto_renew if hasattr(subscription_data, 'auto_renew') else None,
            billing_cycle=subscription_data.billing_cycle if hasattr(subscription_data, 'billing_cycle') else None,
            pause_reason=subscription_data.pause_reason if hasattr(subscription_data, 'pause_reason') else None
            # Add other fields here as needed
        )
        return Response.success(data=subscription.to_dict(include_products=True), message="Subscription updated successfully")
    except APIException as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to update subscription: {str(e)}"
        )
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to update subscription: {str(e)}"
        )
@router.post("/{subscription_id}/cancel")
async def cancel_subscription_endpoint(
    subscription_id: UUID,
    reason: str = None,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Cancel a subscription (soft delete - status update only)."""
    try:
        subscription_service = SubscriptionService(db)
        subscription = await subscription_service.cancel(subscription_id, current_user.id, reason)
        return Response.success(
            data=subscription.to_dict(include_products=True), 
            message="Subscription cancelled successfully"
        )
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"Subscription not found or failed to cancel: {str(e)}"
        )
@router.delete("/{subscription_id}")
async def delete_subscription(
    subscription_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a subscription."""
    try:
        subscription_service = SubscriptionService(db)
        await subscription_service.delete(subscription_id, current_user.id)
        return Response.success(message="Subscription deleted successfully")
    except APIException as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to delete subscription: {str(e)}"
        )
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to delete subscription: {str(e)}"
        )
@router.post("/{subscription_id}/process-shipment")
async def process_subscription_shipment(
    subscription_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Manually trigger shipment processing for a subscription."""
    try:
        subscription_service = SubscriptionService(db)
        subscription = await subscription_service.get(subscription_id, current_user.id)
        if not subscription:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Subscription not found"
            )
        if subscription.status != "active":
            raise APIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Can only process shipments for active subscriptions"
            )
        # Create order from subscription
        scheduler = SubscriptionScheduler(db)
        order = await scheduler.create_subscription_order(subscription)
        if order:
            return Response.success(
                data={
                    "subscription_id": str(subscription_id),
                    "order_id": str(order.id),
                    "order_number": order.order_number
                },
                message="Subscription shipment processed successfully"
            )
        else:
            raise APIException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message="Failed to create order from subscription"
            )
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to process subscription shipment: {str(e)}"
        )
@router.post("/{subscription_id}/pause")
async def pause_subscription(
    subscription_id: UUID,
    pause_reason: str = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Pause a subscription."""
    try:
        subscription_service = SubscriptionService(db)
        subscription = await subscription_service.pause(
            subscription_id, current_user.id, pause_reason
        )
        return Response.success(
            data=subscription.to_dict(include_products=True),
            message="Subscription paused successfully"
        )
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to pause subscription: {str(e)}"
        )
@router.post("/{subscription_id}/resume")
async def resume_subscription(
    subscription_id: UUID,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Resume a paused subscription or activate a cancelled subscription."""
    try:
        subscription_service = SubscriptionService(db)
        subscription = await subscription_service.resume(
            subscription_id, current_user.id
        )
        action_message = "resumed" if subscription.status == "active" else "activated"
        return Response.success(
            data=subscription.to_dict(include_products=True),
            message=f"Subscription {action_message} successfully"
        )
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to resume/activate subscription: {str(e)}"
        )
@router.delete("/{subscription_id}/products/{product_id}")
async def remove_product_from_subscription(
    subscription_id: UUID,
    product_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove a specific product from a subscription."""
    try:
        subscription_service = SubscriptionService(db)
        subscription = await subscription_service.remove_products(
            subscription_id, [product_id], current_user.id
        )
        return Response.success(
            data=subscription.to_dict(include_products=True),
            message="Product removed from subscription successfully"
        )
    except HTTPException as e:
        raise APIException(
            status_code=e.status_code,
            message=e.detail
        )
    except Exception as e:
        logger.error(f"Error removing product from subscription: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to remove product from subscription: {str(e)}"
        )
@router.post("/{subscription_id}/discounts")
async def apply_discount_to_subscription(
    subscription_id: UUID,
    discount_request: DiscountApplicationRequest,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Apply a discount code to a subscription."""
    try:
        raise APIException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            message="Discount application for subscriptions is not yet implemented"
        )
    except HTTPException as e:
        raise APIException(
            status_code=e.status_code,
            message=e.detail
        )
    except Exception as e:
        logger.error(f"Error applying discount to subscription: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to apply discount: {str(e)}"
        )
@router.delete("/{subscription_id}/discounts/{discount_id}")
async def remove_discount_from_subscription(
    subscription_id: UUID,
    discount_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove a discount from a subscription."""
    try:
        raise APIException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            message="Discount removal for subscriptions is not yet implemented"
        )
    except HTTPException as e:
        raise APIException(
            status_code=e.status_code,
            message=e.detail
        )
    except Exception as e:
        logger.error(f"Error removing discount from subscription: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to remove discount: {str(e)}"
        )
@router.get("/{subscription_id}/details")
async def get_subscription_details(
    subscription_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed subscription information for modal display."""
    # Fixed: Using SubscriptionService instead of non-existent EnhancedSubscriptionService
    try:
        subscription_service = SubscriptionService(db)
        # Get subscription with all related data
        subscription = await subscription_service.get(
            subscription_id=subscription_id,
            user_id=current_user.id
        )
        if not subscription:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Subscription not found"
            )
        # Get subscription products/variants
        variant_quantities = subscription.variant_quantities or {}
        products = []
        if variant_quantities:
            # Fetch variant details
            variant_ids = list(variant_quantities.keys())
            result = await db.execute(
                select(ProductVariant)
                .options(selectinload(ProductVariant.product))
                .where(ProductVariant.id.in_(variant_ids))
            )
            variants = result.scalars().all()
            for variant in variants:
                quantity = variant_quantities.get(str(variant.id), 0)
                products.append({
                    "id": str(variant.id),
                    "subscription_id": str(subscription.id),
                    "product_id": str(variant.product_id),
                    "name": variant.product.name,
                    "quantity": quantity,
                    "unit_price": float(variant.price),
                    "total_price": float(variant.price * quantity),
                    "image": variant.product.images[0].image_url if variant.product.images else None,
                    "added_at": subscription.created_at.isoformat()
                })
        # Build response
        details = {
            "subscription": {
                "id": str(subscription.id),
                "name": subscription.name,
                "status": subscription.status,
                "price": float(subscription.price),
                "currency": subscription.currency,
                "billing_cycle": subscription.billing_cycle,
                "auto_renew": subscription.auto_renew,
                "next_billing_date": subscription.next_billing_date.isoformat() if subscription.next_billing_date else None,
                "created_at": subscription.created_at.isoformat(),
                "updated_at": subscription.updated_at.isoformat() if subscription.updated_at else None,
                "subtotal": float(subscription.subtotal) if subscription.subtotal else 0.0,
                "shipping_cost": float(subscription.shipping_cost) if subscription.shipping_cost else 0.0,
                "tax_amount": float(subscription.tax_amount) if subscription.tax_amount else 0.0,
                "total": float(subscription.total) if subscription.total else 0.0,
            },
            "products": products,
            "discounts": []
        }
        return Response.success(
            data=details,
            message="Subscription details retrieved successfully"
        )
    except HTTPException as e:
        raise APIException(
            status_code=e.status_code,
            message=e.detail
        )
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error getting subscription details: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to get subscription details: {str(e)}"
        )
@router.get("/{subscription_id}/orders")
async def get_subscription_orders(
    subscription_id: UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get orders created from a subscription."""
    try:
        subscription_service = SubscriptionService(db)
        orders = await subscription_service.get_orders(
            subscription_id, current_user.id, page, limit
        )
        return Response.success(data=orders)
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch subscription orders: {str(e)}"
        )