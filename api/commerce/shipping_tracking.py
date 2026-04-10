"""
Shipping Tracking API Endpoints
Integrates with multiple shipping companies (UPS, Canada Express, Royal Mail, etc.)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from uuid import UUID

from core.db import get_db
from core.exceptions import APIException
from core.utils.response import Response as APIResponse
from core.dependencies import get_current_auth_user, get_current_admin_user
from models.accounts.user import User
from models.commerce.shipping_tracking import (
    ShipmentTracking, ShippingProvider, ShippingCarrier, 
    TrackingStatus, ShipmentType
)
from services.commerce.shipping_tracking import ShippingTrackingService
from datetime import datetime

from schemas.commerce.shipping_tracking import (
    Create,
    Update,
    Track
)

router = APIRouter(prefix="/shipping-tracking", tags=["Shipping Tracking"])

def get_shipping_tracking_service(db: AsyncSession = Depends(get_db)):
    return ShippingTrackingService(db)

@router.post("/shipments")
async def create_shipment(
    shipment_data: Create,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_auth_user),
    shipping_service: ShippingTrackingService = Depends(get_shipping_tracking_service)
):
    """Create a new shipment tracking record"""
    try:
        # Convert string IDs to UUID
        shipment_dict = shipment_data.dict()
        shipment_dict['order_id'] = UUID(shipment_dict['order_id'])
        if shipment_dict.get('order_item_id'):
            shipment_dict['order_item_id'] = UUID(shipment_dict['order_item_id'])
        
        shipment = await shipping_service.create_shipment(shipment_dict)
        
        # Trigger initial tracking in background
        background_tasks.add_task(
            track_shipment_background,
            shipment.tracking_number,
            shipment.carrier
        )
        
        return APIResponse.success(
            data=shipment.to_dict(),
            message="Shipment created successfully"
        )
    
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=500,
            message=f"Failed to create shipment: {str(e)}"
        )

@router.get("/shipments/{shipment_id}")
async def get(
    shipment_id: str,
    current_user: User = Depends(get_current_auth_user),
    shipping_service: ShippingTrackingService = Depends(get_shipping_tracking_service)
):
    """Get detailed tracking information for a shipment"""
    try:
        shipment = await shipping_service.get_shipment_tracking(shipment_id)
        
        if not shipment:
            raise HTTPException(status_code=404, detail="Shipment not found")
        
        return APIResponse.success(data=shipment)
    
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=500,
            message=f"Failed to get shipment tracking: {str(e)}"
        )

@router.get("/orders/{order_id}/shipments")
async def get_order_shipments(
    order_id: str,
    current_user: User = Depends(get_current_auth_user),
    shipping_service: ShippingTrackingService = Depends(get_shipping_tracking_service)
):
    """Get all shipments for an order"""
    try:
        shipments = await shipping_service.get_order_shipments(order_id)
        return APIResponse.success(data=shipments)
    
    except Exception as e:
        raise APIException(
            status_code=500,
            message=f"Failed to get order shipments: {str(e)}"
        )

@router.post("/track")
async def track_shipment(
    tracking_request: Track,
    current_user: User = Depends(get_current_auth_user),
    shipping_service: ShippingTrackingService = Depends(get_shipping_tracking_service)
):
    """Track a shipment using carrier-specific integration"""
    try:
        tracking_data = await shipping_service.track_shipment(
            tracking_request.tracking_number,
            tracking_request.carrier
        )
        
        return APIResponse.success(
            data=tracking_data,
            message="Tracking information retrieved successfully"
        )
    
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=500,
            message=f"Failed to track shipment: {str(e)}"
        )

@router.patch("/shipments/{shipment_id}/status")
async def update_shipment_status(
    shipment_id: str,
    update_data: Update,
    current_user: User = Depends(get_current_auth_user),
    shipping_service: ShippingTrackingService = Depends(get_shipping_tracking_service)
):
    """Update shipment status and create tracking event"""
    try:
        shipment = await shipping_service.update_shipment_status(
            shipment_id,
            update_data.status,
            update_data.dict(exclude={'status'})
        )
        
        return APIResponse.success(
            data=shipment.to_dict(),
            message="Shipment status updated successfully"
        )
    
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=500,
            message=f"Failed to update shipment status: {str(e)}"
        )

@router.get("/carriers")
async def list_carriers(
    db: AsyncSession = Depends(get_db)
):
    """Get list of supported shipping carriers (public)"""
    try:
        result = await db.execute(
            select(ShippingProvider).where(ShippingProvider.is_active == True)
        )
        providers = result.scalars().all()

        carriers = []
        for provider in providers:
            carriers.append({
                "carrier": provider.carrier.value,
                "name": provider.name,
                "api_url": provider.api_url,
                "tracking_url_template": provider.tracking_url_template
            })

        return APIResponse.success(data=carriers)

    except Exception as e:
        raise APIException(
            status_code=500,
            message=f"Failed to get supported carriers: {str(e)}"
        )


@router.get("/shipments")
async def list(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """List shipments visible to the current user"""
    try:
        from sqlalchemy import select as sa_select, func
        from models.commerce.orders import Order

        base_query = (
            sa_select(ShipmentTracking)
            .join(Order, ShipmentTracking.order_id == Order.id)
            .where(Order.user_id == current_user.id)
        )
        count_query = (
            sa_select(func.count())
            .select_from(ShipmentTracking)
            .join(Order, ShipmentTracking.order_id == Order.id)
            .where(Order.user_id == current_user.id)
        )

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        result = await db.execute(
            base_query.order_by(ShipmentTracking.created_at.desc())
            .offset((page - 1) * limit).limit(limit)
        )
        shipments = result.scalars().all()

        return APIResponse.success(data=[s.to_dict() for s in shipments], pagination={
            "page": page,
            "limit": limit,
            "total": total,
            "pages": max(1, (total + limit - 1) // limit)
        })
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to list shipments: {str(e)}")

@router.post("/providers")
async def create_provider(
    provider_data: dict,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new shipping provider (Admin only)"""
    try:
        provider = ShippingProvider(
            name=provider_data['name'],
            carrier=provider_data['carrier'],
            api_key=provider_data.get('api_key'),
            api_secret=provider_data.get('api_secret'),
            api_url=provider_data['api_url'],
            tracking_url_template=provider_data['tracking_url_template'],
            webhook_url=provider_data.get('webhook_url'),
            is_active=provider_data.get('is_active', True),
            configuration=provider_data.get('configuration', {}),
            rate_limits=provider_data.get('rate_limits', {})
        )
        
        db.add(provider)
        await db.commit()
        
        return APIResponse.success(
            data=provider.to_dict(),
            message="Shipping provider created successfully"
        )
    
    except Exception as e:
        await db.rollback()
        raise APIException(
            status_code=500,
            message=f"Failed to create shipping provider: {str(e)}"
        )

@router.get("/providers")
async def list_providers(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all shipping providers (Admin only)"""
    try:
        result = await db.execute(select(ShippingProvider))
        providers = result.scalars().all()
        
        return APIResponse.success(
            data=[provider.to_dict() for provider in providers]
        )
    
    except Exception as e:
        raise APIException(
            status_code=500,
            message=f"Failed to get shipping providers: {str(e)}"
        )

@router.patch("/providers/{provider_id}")
async def patch_provider(
    provider_id: str,
    provider_data: dict,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a shipping provider (Admin only)"""
    try:
        result = await db.execute(
            select(ShippingProvider).where(ShippingProvider.id == UUID(provider_id))
        )
        provider = result.scalar_one_or_none()
        
        if not provider:
            raise HTTPException(status_code=404, detail="Shipping provider not found")
        
        # Update provider fields
        for field, value in provider_data.items():
            if hasattr(provider, field):
                setattr(provider, field, value)
        
        await db.commit()
        
        return APIResponse.success(
            data=provider.to_dict(),
            message="Shipping provider updated successfully"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise APIException(
            status_code=500,
            message=f"Failed to update shipping provider: {str(e)}"
        )

@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a shipping provider (Admin only)"""
    try:
        result = await db.execute(
            select(ShippingProvider).where(ShippingProvider.id == UUID(provider_id))
        )
        provider = result.scalar_one_or_none()
        
        if not provider:
            raise HTTPException(status_code=404, detail="Shipping provider not found")
        
        await db.delete(provider)
        await db.commit()
        
        return APIResponse.success(
            message="Shipping provider deleted successfully"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise APIException(
            status_code=500,
            message=f"Failed to delete shipping provider: {str(e)}"
        )

# Background task for tracking shipments
async def track_shipment_background(tracking_number: str, carrier: ShippingCarrier):
    """Background task to track shipments"""
    from core.db import AsyncSessionDB
    
    if not AsyncSessionDB:
        print(f"Background tracking skipped for {tracking_number}: DB not initialized")
        return
    
    async with AsyncSessionDB() as db:
        try:
            shipping_service = ShippingTrackingService(db)
            await shipping_service.track_shipment(tracking_number, carrier)
        except Exception as e:
            print(f"Background tracking failed for {tracking_number}: {e}")

# ==========================================================
# ORDER TRACKING - From orders module
# ==========================================================
@router.get("/orders/{order_id}")
async def get_order_tracking(
    order_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get order tracking information (authenticated)."""
    try:
        # Get order from orders service
        from services.commerce.orders import OrderService
        order_service = OrderService(db)
        tracking = await order_service.tracking(order_id, current_user.id)
        if tracking is None:
            raise APIException(status_code=404, message="Order not found or tracking unavailable")
        return APIResponse.success(data=tracking)
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to fetch tracking: {str(e)}")


@router.get("/track/{order_id}")
async def get_public_tracking(
    order_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get order tracking (public - no auth required)."""
    try:
        from services.commerce.orders import OrderService
        order_service = OrderService(db)
        tracking = await order_service.tracking_public(order_id)
        return APIResponse.success(data=tracking)
    except Exception:
        raise APIException(status_code=404, message="Order not found or tracking unavailable")


# Webhook endpoints for carrier notifications
@router.post("/webhooks/{carrier}")
async def handle_carrier_webhook(
    carrier: ShippingCarrier,
    webhook_data: dict,
    db: AsyncSession = Depends(get_db)
):
    """Handle webhook notifications from shipping carriers"""
    try:
        # Verify webhook signature if applicable
        # Process webhook data
        # Update shipment tracking
        
        return APIResponse.success(
            message="Webhook processed successfully"
        )
    
    except Exception as e:
        raise APIException(
            status_code=500,
            message=f"Failed to process webhook: {str(e)}"
        )
