"""Shipping tracking API endpoints; integrates with multiple carriers (UPS, Royal Mail, etc.)."""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID

from core.db import get_db
from core.exceptions import APIException
from core.utils.response import Response as APIResponse
from core.logging import get_structured_logger
from core.dependencies import require_admin, require_auth
from models.accounts.user import User
from models.commerce.shipping_tracking import ShippingProvider, ShipmentTracking

from services.commerce.shipping_tracking import ShippingTrackingService
from services.commerce.carriers import CarrierService
from datetime import datetime

from schemas.commerce.shipping_tracking import (
    Create,
    Update,
    Track
)
from schemas.commerce.carrier import Create as CarrierCreate, Update as CarrierUpdate

logger = get_structured_logger(__name__)

router = APIRouter(prefix="/shipping-tracking", tags=["shipping-tracking"])

@router.post("/shipments/")
async def create_shipment(
    shipment_data: Create,
    background_tasks: BackgroundTasks,
    current_user = Depends(require_auth),
    db: AsyncSession = Depends(get_db)
):
    """Create a new shipment tracking record"""
    try:
        shipping_service = ShippingTrackingService(db)
        # Convert string IDs to UUID
        shipment_dict = shipment_data.dict()
        shipment_dict['order_id'] = UUID(shipment_dict['order_id'])
        if shipment_dict.get('order_item_id'):
            shipment_dict['order_item_id'] = UUID(shipment_dict['order_item_id'])
        
        shipment = await shipping_service.create(shipment_dict)
        
        # Trigger initial tracking in background
        background_tasks.add_task(
            track_shipment_background,
            shipment.tracking_number,
            shipment_dict['carrier']
        )
        
        return APIResponse.success(
            data=shipment.to_dict(),
            message="Shipment created successfully"
        )
    
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=500,
            message=f"Failed to create shipment: {str(e)}"
        )

@router.get("/shipments/{shipment_id}/")
async def get_shipment(
    shipment_id: str,
    current_user = Depends(require_auth),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed tracking information for a shipment"""
    try:
        shipping_service = ShippingTrackingService(db)
        shipment = await shipping_service.get(str(shipment_id))
        
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

@router.post("/track/")
async def track(
    tracking_request: Track,
    current_user = Depends(require_auth),
    db: AsyncSession = Depends(get_db)
):
    """Track a shipment using carrier-specific integration"""
    try:
        shipping_service = ShippingTrackingService(db)
        tracking_info = await shipping_service.track_shipment(
            tracking_request.tracking_number,
            tracking_request.carrier
        )
        
        return APIResponse.success(
            data=tracking_info,
            message="Tracking information retrieved successfully"
        )
    
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=500,
            message=f"Failed to track shipment: {str(e)}"
        )

@router.patch("/shipments/{shipment_id}/status/")
async def update_shipment_status(
    shipment_id: str,
    update_data: Update,
    current_user = Depends(require_auth),
    db: AsyncSession = Depends(get_db)
):
    """Update shipment status and create tracking event"""
    try:
        shipping_service = ShippingTrackingService(db)
        shipment = await shipping_service.update(
            str(shipment_id),
            update_data.status,
            update_data.dict(exclude={'status'})
        )
        
        return APIResponse.success(
            data=shipment.to_dict(),
            message="Shipment status updated successfully"
        )
    
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=500,
            message=f"Failed to update shipment status: {str(e)}"
        )

@router.get("/carriers/")
async def list_carriers(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db)
):
    """Get list of supported shipping carriers (public)"""
    try:
        carriers, total = await CarrierService(db).list(limit=200, active_only=active_only)
        return APIResponse.success(data=[c.to_dict() for c in carriers], pagination={"total": total})
    except Exception as e:
        raise APIException(
            status_code=500,
            message=f"Failed to get supported carriers: {str(e)}"
        )


@router.post("/carriers/")
async def create_carrier(
    carrier_data: CarrierCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new carrier (Admin only)"""
    carrier = await CarrierService(db).create(carrier_data)
    return APIResponse.success(data=carrier.to_dict(), message="Carrier created successfully")


@router.patch("/carriers/{carrier_id}/")
async def update_carrier(
    carrier_id: UUID,
    carrier_data: CarrierUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a carrier (Admin only)"""
    carrier = await CarrierService(db).update(carrier_id, carrier_data)
    if not carrier:
        raise HTTPException(status_code=404, detail="Carrier not found")
    return APIResponse.success(data=carrier.to_dict(), message="Carrier updated successfully")


@router.delete("/carriers/{carrier_id}/")
async def delete_carrier(
    carrier_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a carrier (Admin only). Fails if any provider still references it."""
    deleted = await CarrierService(db).delete(carrier_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Carrier not found")
    return APIResponse.success(message="Carrier deleted successfully")


@router.get("/shipments/")
async def list(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_auth),
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
            .options(
                selectinload(ShipmentTracking.tracking_events),
                selectinload(ShipmentTracking.carrier),
                selectinload(ShipmentTracking.provider),
            )
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

@router.post("/providers/")
async def create_provider(
    provider_data: dict,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new shipping provider (Admin only)"""
    try:
        carrier = await CarrierService(db).get_by_code(provider_data['carrier'])
        if not carrier:
            raise HTTPException(status_code=404, detail=f"Carrier '{provider_data['carrier']}' not found")

        provider = ShippingProvider(
            name=provider_data['name'],
            carrier_id=carrier.id,
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

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise APIException(
            status_code=500,
            message=f"Failed to create shipping provider: {str(e)}"
        )

@router.get("/providers/")
async def list_providers(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all shipping providers (Admin only)"""
    try:
        result = await db.execute(select(ShippingProvider).options(selectinload(ShippingProvider.carrier)))
        providers = result.scalars().all()
        
        return APIResponse.success(
            data=[provider.to_dict() for provider in providers]
        )
    
    except Exception as e:
        raise APIException(
            status_code=500,
            message=f"Failed to get shipping providers: {str(e)}"
        )

@router.patch("/providers/{provider_id}/")
async def patch_provider(
    provider_id: str,
    provider_data: dict,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a shipping provider (Admin only)"""
    try:
        result = await db.execute(
            select(ShippingProvider)
            .where(ShippingProvider.id == UUID(provider_id))
            .options(selectinload(ShippingProvider.carrier))
        )
        provider = result.scalar_one_or_none()

        if not provider:
            raise HTTPException(status_code=404, detail="Shipping provider not found")

        # Carrier is passed as a code (e.g. "ups") and resolved to its id
        if 'carrier' in provider_data:
            carrier = await CarrierService(db).get_by_code(provider_data.pop('carrier'))
            if not carrier:
                raise HTTPException(status_code=404, detail="Carrier not found")
            provider.carrier_id = carrier.id

        # Update remaining provider fields
        for field, value in provider_data.items():
            if field != 'id' and hasattr(provider, field):
                setattr(provider, field, value)

        await db.commit()

        # Re-fetch with carrier eager-loaded: committing a dirty object expires its
        # relationships even with expire_on_commit=False, so to_dict() would otherwise crash.
        result = await db.execute(
            select(ShippingProvider)
            .where(ShippingProvider.id == provider.id)
            .options(selectinload(ShippingProvider.carrier))
        )
        provider = result.scalar_one()

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

@router.delete("/providers/{provider_id}/")
async def delete_provider(
    provider_id: str,
    current_user: User = Depends(require_admin),
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
async def track_shipment_background(tracking_number: str, carrier: str):
    """Background task to track shipments"""
    from core.db import AsyncSessionDB
    
    if not AsyncSessionDB:
        logger.warning(f"Background tracking skipped for {tracking_number}: DB not initialized")
        return

    async with AsyncSessionDB() as db:
        try:
            shipping_service = ShippingTrackingService(db)
            await shipping_service.track_shipment(tracking_number, carrier)
        except Exception as e:
            logger.error(f"Background tracking failed for {tracking_number}: {e}")

# Webhook endpoints for carrier notifications
@router.post("/webhooks/{carrier}/")
async def handle_carrier_webhook(
    carrier: str,
    webhook_data: dict,
    db: AsyncSession = Depends(get_db)
):
    """Handle webhook notifications from shipping carriers"""
    try:
        # TODO: verify signature, process data, and update tracking.
        return APIResponse.success(
            message="Webhook processed successfully"
        )
    
    except Exception as e:
        raise APIException(
            status_code=500,
            message=f"Failed to process webhook: {str(e)}"
        )
