from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from core.db import get_db
from core.utils.response import Response
from core.errors import APIException
from core.logging import get_logger
from core.dependencies import require_admin_or_supplier, get_inventory_service
from models.user import User

from schemas.inventory import (
    WarehouseLocationCreate, WarehouseLocationUpdate, WarehouseLocationResponse,
    InventoryCreate, InventoryUpdate, InventoryResponse,
    StockAdjustmentCreate, StockAdjustmentResponse
)
from services.inventory import InventoryService

logger = get_logger(__name__)

router = APIRouter(prefix="/inventory", tags=["Inventory Management"])


# --- Public Stock Check Endpoint ---
@router.get("/check-stock/{variant_id}")
async def check_stock_availability(
    variant_id: UUID,
    quantity: int = Query(..., gt=0, description="Quantity to check"),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Check stock availability for a product variant (Public endpoint)."""
    try:
        # Validate variant_id format
        if not variant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid variant ID provided"
            )
        
        stock_check = await inventory_service.check_stock_availability(variant_id, quantity)
        return Response.success(data=stock_check, message="Stock check completed")
    except ValueError as e:
        # Handle invalid UUID format
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid variant ID format"
        )
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Failed to check stock: {e}"
        )


# --- Bulk Stock Check Endpoint for Checkout ---
@router.post("/check-stock/bulk")
async def check_bulk_stock_availability(
    items: List[dict],
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Check stock availability for multiple items at once (Public endpoint for Checkout)."""
    try:
        results = []
        
        for item in items:
            variant_id = item.get("variant_id")
            quantity = item.get("quantity", 1)
            
            if not variant_id:
                results.append({
                    "variant_id": None,
                    "available": False,
                    "message": "Invalid variant ID",
                    "stock_status": "error"
                })
                continue
            
            try:
                stock_check = await inventory_service.check_stock_availability(
                    UUID(variant_id), quantity
                )
                results.append({
                    "variant_id": str(variant_id),
                    "quantity_requested": quantity,
                    **stock_check
                })
            except Exception as e:
                results.append({
                    "variant_id": str(variant_id),
                    "quantity_requested": quantity,
                    "available": False,
                    "message": f"Stock check failed: {str(e)}",
                    "stock_status": "error"
                })
        
        # Calculate overall availability
        all_available = all(result.get("available", False) for result in results)
        unavailable_count = sum(1 for result in results if not result.get("available", False))
        
        return Response.success(
            data={
                "items": results,
                "all_available": all_available,
                "unavailable_count": unavailable_count,
                "total_items": len(results)
            },
            message="Bulk stock check completed"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check bulk stock: {e}"
        )


# --- WarehouseLocation Endpoints ---
@router.post("/locations")
async def create_warehouse_location(
    location_data: WarehouseLocationCreate,
    current_user: User = Depends(require_admin_or_supplier),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Create a new warehouse location (Admin/Supplier access)."""
    try:
        location = await inventory_service.create_warehouse_location(location_data)
        return Response.success(data=location, message="Warehouse location created successfully", status_code=status.HTTP_201_CREATED)
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create location: {e}")


@router.get("/locations")
async def get_all_warehouse_locations(
    current_user: User = Depends(require_admin_or_supplier),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Get all warehouse locations (Admin/Supplier access)."""
    try:
        locations = await inventory_service.get_warehouse_locations()
        return Response.success(data=locations)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch locations: {e}")


@router.get("/locations/{location_id}")
async def get_warehouse_location(
    location_id: UUID,
    current_user: User = Depends(require_admin_or_supplier),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Get a specific warehouse location by ID (Admin/Supplier access)."""
    try:
        location = await inventory_service.get_warehouse_location_by_id(location_id)
        if not location:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND, message="Warehouse location not found")
        return Response.success(data=location)
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch location: {e}")


@router.put("/locations/{location_id}")
async def update_warehouse_location(
    location_id: UUID,
    location_data: WarehouseLocationUpdate,
    current_user: User = Depends(require_admin_or_supplier),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Update a warehouse location (Admin/Supplier access)."""
    try:
        location = await inventory_service.update_warehouse_location(location_id, location_data)
        return Response.success(data=location, message="Warehouse location updated successfully")
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update location: {e}")


@router.delete("/locations/{location_id}")
async def delete_warehouse_location(
    location_id: UUID,
    current_user: User = Depends(require_admin_or_supplier),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Delete a warehouse location (Admin/Supplier access)."""
    try:
        await inventory_service.delete_warehouse_location(location_id)
        return Response.success(message="Warehouse location deleted successfully")
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete location: {e}")


# --- Inventory Item Endpoints ---
# --- Inventory CRUD Endpoints ---
@router.post("/")
async def create_inventory_item(
    inventory_data: InventoryCreate,
    current_user: User = Depends(require_admin_or_supplier),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Create a new inventory item (Admin/Supplier access)."""
    try:
        item = await inventory_service.create_inventory_item(inventory_data)
        return Response.success(data=item, message="Inventory item created successfully", status_code=status.HTTP_201_CREATED)
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create inventory item: {e}")


@router.get("/")
async def get_all_inventory_items(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    product_id: Optional[UUID] = Query(None),
    location_id: Optional[UUID] = Query(None),
    low_stock: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None, regex="^(updated_at|created_at|product_name|quantity|location_name)$"),
    sort_order: Optional[str] = Query(None, regex="^(asc|desc)$"),
    current_user: User = Depends(require_admin_or_supplier),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Get all inventory items with filters (Admin/Supplier access)."""
    try:
        logger.info(f"API endpoint received params: page={page}, limit={limit}, sort_by={sort_by}, sort_order={sort_order}, low_stock={low_stock}, search={search}")
        items = await inventory_service.get_all_inventory_items(
            page=page,
            limit=limit,
            product_id=product_id,
            location_id=location_id,
            low_stock=low_stock,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order
        )
        return Response.success(data=items)
    except APIException:
        raise
    except Exception as e:
        logger.exception("Failed to fetch inventory items")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch inventory items: {e}")


@router.get("/{inventory_id}")
async def get_inventory_item(
    inventory_id: UUID,
    current_user: User = Depends(require_admin_or_supplier),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Get a specific inventory item by ID (Admin/Supplier access)."""
    try:
        item = await inventory_service.get_inventory_item_by_id_serialized(inventory_id)
        if not item:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND, message="Inventory item not found")
        return Response.success(data=item)
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch inventory item: {e}")


@router.put("/{inventory_id}")
async def update_inventory_item(
    inventory_id: UUID,
    inventory_data: InventoryUpdate,
    current_user: User = Depends(require_admin_or_supplier),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Update an inventory item (Admin/Supplier access)."""
    try:
        item = await inventory_service.update_inventory_item(inventory_id, inventory_data)
        return Response.success(data=item, message="Inventory item updated successfully")
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update inventory item: {e}")


@router.delete("/{inventory_id}")
async def delete_inventory_item(
    inventory_id: UUID,
    current_user: User = Depends(require_admin_or_supplier),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Delete an inventory item (Admin/Supplier access)."""
    try:
        await inventory_service.delete_inventory_item(inventory_id)
        return Response.success(message="Inventory item deleted successfully")
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete inventory item: {e}")


# --- Stock Adjustment Endpoints ---
@router.post("/adjustments")
async def adjust_stock(
    adjustment_data: StockAdjustmentCreate,
    current_user: User = Depends(require_admin_or_supplier),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Adjust stock quantity for an inventory item (Admin/Supplier access)."""
    try:
        updated_inventory = await inventory_service.adjust_stock(adjustment_data, adjusted_by_user_id=current_user.id)
        return Response.success(data=updated_inventory, message="Stock adjusted successfully")
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to adjust stock: {e}")


@router.get("/{inventory_id}/adjustments")
async def get_stock_adjustments(
    inventory_id: UUID,
    current_user: User = Depends(require_admin_or_supplier),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Get all stock adjustments for an inventory item (Admin/Supplier access)."""
    try:
        adjustments = await inventory_service.get_stock_adjustments_for_inventory(inventory_id)
        return Response.success(data=adjustments)
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch stock adjustments: {e}")


@router.get("/adjustments/all")
async def get_all_stock_adjustments(
    current_user: User = Depends(require_admin_or_supplier),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Get all stock adjustments across all inventory items (Admin/Supplier access)."""
    try:
        adjustments = await inventory_service.get_all_stock_adjustments()
        return Response.success(data=adjustments)
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch all stock adjustments: {e}")


# --- Warehouse Location Endpoints ---
# (Already defined above, removing duplicates)