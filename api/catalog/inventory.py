from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID, UUID as UUIDType

from core.db import get_db
from core.dependencies import get_current_auth_user, require_admin
from core.utils.response import Response
from core.exceptions import APIException
from core.logging import get_structured_logger as get_logger
from schemas.catalog.inventory import (
    LocationCreate, LocationUpdate, LocationResponse,
    Create, Update, Response as InventoryResponse,
    AdjustmentCreate, AdjustmentResponse
)
from services.catalog.inventory import InventoryService
from models.accounts.user import UserRole, User

logger = get_logger(__name__)

router = APIRouter(prefix="/inventory", tags=["inventory"])


# ==========================================================
# LOCATIONS - 5 Standard APIs
# ==========================================================
@router.post("/locations/")
async def create_location(
    location_data: LocationCreate,
    current_user = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
) -> Response:
    """Create a new warehouse location (Admin access)."""
    try:
        inventory_service = InventoryService(db)
        location = await inventory_service.create_location(location_data)
        return Response.success(data=location, message="Warehouse location created successfully", status_code=status.HTTP_201_CREATED)
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create location: {e}")


@router.get("/locations/{location_id}/")
async def get_location(
    location_id: UUID,
    current_user: Optional[User] = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
) -> Response:
    """Get a specific warehouse location by ID."""
    try:
        inventory_service = InventoryService(db)
        location = await inventory_service.get_location(location_id)
        if not location:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND, message="Warehouse location not found")
        return Response.success(data=location, message="Warehouse location retrieved successfully")
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch location: {e}")


@router.get("/locations/")
async def list_locations(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """List all warehouse locations with pagination."""
    try:
        inventory_service = InventoryService(db)
        result = await inventory_service.list_locations(page=page, limit=limit)
        if isinstance(result, dict) and "data" in result and "pagination" in result:
            return Response.success(data=result.get("data", []), pagination=result.get("pagination"), message="Warehouse locations retrieved successfully")
        return Response.success(data=result, message="Warehouse locations retrieved successfully")
    except Exception as e:
        logger.error(f"Error fetching locations: {e}", exc_info=True)
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message="Failed to fetch locations")


@router.patch("/locations/{location_id}/")
async def update_location(
    location_id: UUID,
    location_data: LocationUpdate,
    current_user = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
) -> Response:
    """Partially update a warehouse location (Admin access)."""
    try:
        inventory_service = InventoryService(db)
        location = await inventory_service.update_location(location_id, location_data)
        return Response.success(data=location, message="Warehouse location updated successfully")
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update location: {e}")


@router.delete("/locations/{location_id}/")
async def delete_location(
    location_id: UUID,
    current_user = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
) -> Response:
    """Delete a warehouse location (Admin access)."""
    try:
        inventory_service = InventoryService(db)
        await inventory_service.delete_location(location_id)
        return Response.success(message="Warehouse location deleted successfully")
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete location: {e}")


# ==========================================================
# INVENTORY - 5 Standard APIs
# ==========================================================
@router.post("/")
async def create(
    inventory_data: Create,
    current_user = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
) -> InventoryResponse:
    """Create a new inventory item (Admin access)."""
    try:
        inventory_service = InventoryService(db)
        item = await inventory_service.create(inventory_data)
        return Response.success(data=item, message="Inventory item created successfully", status_code=status.HTTP_201_CREATED)
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create inventory item: {e}")


@router.get("/{inventory_id}/")
async def get(
    inventory_id: UUID,
    current_user: Optional[User] = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
) -> Response:
    """Get a specific inventory item by ID."""
    try:
        inventory_service = InventoryService(db)
        item = await inventory_service.get(inventory_id, serialized=True)
        if not item:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND, message="Inventory item not found")
        return Response.success(data=item, message="Inventory item retrieved successfully")
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch inventory item: {e}")


@router.get("/")
async def list(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    product_id: Optional[UUID] = Query(None),
    location_id: Optional[UUID] = Query(None),
    location_name: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    low_stock: Optional[bool] = Query(None),
    in_stock: Optional[bool] = Query(None),
    out_of_stock: Optional[bool] = Query(None),
    sort_by: Optional[str] = Query(None, regex="^(updated_at|created_at|product_name|quantity|location_name)$"),
    sort_order: Optional[str] = Query(None, regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db)
):
    """List inventory items with filters."""
    try:
        inventory_service = InventoryService(db)
        items = await inventory_service.list(
            page=page,
            limit=limit,
            product_id=product_id,
            location_id=location_id,
            location_name=location_name,
            search=search,
            low_stock=low_stock,
            in_stock=in_stock,
            out_of_stock=out_of_stock,
            sort_by=sort_by,
            sort_order=sort_order
        )
        if isinstance(items, dict) and "data" in items:
            pagination = {
                "page": items.get("page", page),
                "limit": items.get("limit", limit),
                "total": items.get("total", 0),
                "pages": items.get("pages", 1)
            }
            return Response.success(data=items.get("data", []), pagination=pagination, message="Inventory items retrieved successfully")
        return Response.success(data=items, message="Inventory items retrieved successfully")
    except Exception as e:
        logger.error(f"Error fetching inventory items: {e}", exc_info=True)
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message="Failed to fetch inventory items")


@router.patch("/{inventory_id}/")
async def patch(
    inventory_id: UUID,
    inventory_data: Update,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
) -> Response:
    """Partially update an inventory item (Admin access)."""
    try:
        inventory_service = InventoryService(db)
        item = await inventory_service.update(inventory_id, inventory_data)
        return Response.success(data=item, message="Inventory item updated successfully")
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update inventory item: {e}")


@router.delete("/{inventory_id}/")
async def delete(
    inventory_id: UUID,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
) -> Response:
    """Delete an inventory item (Admin access)."""
    try:
        inventory_service = InventoryService(db)
        await inventory_service.delete(inventory_id)
        return Response.success(message="Inventory item deleted successfully")
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete inventory item: {e}")


# ==========================================================
# ADJUSTMENTS - 5 Standard APIs
# ==========================================================
@router.post("/adjustments/")
async def create_adj(
    adjustment_data: AdjustmentCreate,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
) -> Response:
    """Create a stock adjustment (Admin access)."""
    try:
        inventory_service = InventoryService(db)
        updated_inventory = await inventory_service.adjust_stock(adjustment_data, adjusted_by_user_id=current_user.id)
        return Response.success(data=updated_inventory, message="Stock adjusted successfully")
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to adjust stock: {e}")


@router.get("/adjustments/{adjustment_id}/")
async def get_adj(
    adjustment_id: UUID,
    current_user: Optional[User] = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
) -> Response:
    """Get a specific stock adjustment by ID (Admin access)."""
    try:
        inventory_service = InventoryService(db)
        adjustment = await inventory_service.get_adjustment(adjustment_id)
        if not adjustment:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND, message="Stock adjustment not found")
        return Response.success(data=adjustment, message="Stock adjustment retrieved successfully")
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch stock adjustment: {e}")


@router.get("/adjustments/")
async def list_adj(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    inventory_id: Optional[UUID] = Query(None),
    current_user: Optional[User] = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
) -> Response:
    """List all stock adjustments with pagination (Admin access)."""
    try:
        inventory_service = InventoryService(db)
        result = await inventory_service.adjustments(inventory_id=inventory_id, page=page, limit=limit)
        if isinstance(result, dict) and "data" in result and "pagination" in result:
            return Response.success(data=result.get("data", []), pagination=result.get("pagination"), message="Stock adjustments retrieved successfully")
        return Response.success(data=result, message="Stock adjustments retrieved successfully")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch stock adjustments: {e}")


@router.delete("/adjustments/{adjustment_id}/")
async def delete_adj(
    adjustment_id: UUID,
    current_user: Optional[User] = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
) -> Response:
    """Delete a stock adjustment (Admin access)."""
    try:
        inventory_service = InventoryService(db)
        deleted = await inventory_service.delete_adjustment(adjustment_id)
        if not deleted:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND, message="Stock adjustment not found")
        return Response.success(message="Stock adjustment deleted successfully")
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete stock adjustment: {e}")


# ==========================================================
# INVENTORY SYNC ENDPOINTS - Moved from admin.py
# ==========================================================

@router.post("/sync-all/")
async def sync_all(
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
) -> Response:
    """
    Sync all product availability statuses based on current inventory levels.
    Admin only - for data consistency maintenance.
    """
    try:
        inventory_service = InventoryService(db)
        result = await inventory_service.sync()
        
        return Response.success(
            data=result,
            message=result.get("message", "Inventory sync completed")
        )
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to sync inventory: {str(e)}"
        )


@router.post("/sync/product/{product_id}/")
async def sync_product(
    product_id: str,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
) -> Response:
    """
    Sync a single product's availability status based on its variant inventory levels.
    Admin only - for data consistency maintenance.
    """
    try:
        product_id_uuid = UUIDType(product_id)
        inventory_service = InventoryService(db)
        result = await inventory_service.sync(product_id_uuid)
        
        return Response.success(
            data=result,
            message="Product inventory synced successfully"
        )
    except ValueError:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Invalid product ID format"
        )
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to sync product inventory: {str(e)}"
        )