from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from core.db import get_db
from core.utils.response import Response
from core.exceptions import APIException
from core.logging import get_structured_logger as get_logger
from models.accounts.user import User
from services.accounts.auth import AuthService
from fastapi.security import OAuth2PasswordBearer
from schemas.catalog.inventory import (
    LocationCreate, LocationUpdate, LocationResponse,
    Create, Update, Response,
    AdjustmentCreate, AdjustmentResponse
)
from services.catalog.inventory import InventoryService

logger = get_logger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_auth_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    auth_service = AuthService(db)
    return await auth_service.current_user(token)

def require_admin(current_user: User = Depends(get_current_auth_user)):
    from models.accounts.user import UserRole
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise APIException(status_code=403, message="Admin access required")
    return current_user

def get_inventory_service(db: AsyncSession = Depends(get_db)):
    return InventoryService(db)

router = APIRouter(prefix="/inventory", tags=["Inventory Management"])


# ==========================================================
# LOCATIONS - 5 Standard APIs
# ==========================================================
@router.post("/locations")
async def create(
    location_data: LocationCreate,
    current_user: User = Depends(require_admin),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Create a new warehouse location (Admin access)."""
    try:
        location = await inventory_service.create_location(location_data)
        return Response.success(data=location, message="Warehouse location created successfully", status_code=status.HTTP_201_CREATED)
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create location: {e}")


@router.get("/locations/{location_id}")
async def get(
    location_id: UUID,
    current_user: User = Depends(require_admin),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Get a specific warehouse location by ID (Admin access)."""
    try:
        location = await inventory_service.get_location(location_id)
        if not location:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND, message="Warehouse location not found")
        return Response.success(data=location)
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch location: {e}")


@router.get("/locations")
async def list(
    current_user: User = Depends(require_admin),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """List all warehouse locations (Admin access)."""
    try:
        locations = await inventory_service.list_locations()
        return Response.success(data=locations)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch locations: {e}")


@router.patch("/locations/{location_id}")
async def patch(
    location_id: UUID,
    location_data: LocationUpdate,
    current_user: User = Depends(require_admin),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Partially update a warehouse location (Admin access)."""
    try:
        location = await inventory_service.update_location(location_id, location_data)
        return Response.success(data=location, message="Warehouse location updated successfully")
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update location: {e}")


@router.delete("/locations/{location_id}")
async def delete(
    location_id: UUID,
    current_user: User = Depends(require_admin),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Delete a warehouse location (Admin access)."""
    try:
        await inventory_service.delete_location(location_id)
        return Response.success(message="Warehouse location deleted successfully")
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete location: {e}")


# ==========================================================
# INVENTORY - 5 Standard APIs
# ==========================================================
@router.post("/")
async def create(
    inventory_data: Create,
    current_user: User = Depends(require_admin),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Create a new inventory item (Admin access)."""
    try:
        item = await inventory_service.create(inventory_data)
        return Response.success(data=item, message="Inventory item created successfully", status_code=status.HTTP_201_CREATED)
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create inventory item: {e}")


@router.get("/{inventory_id}")
async def get(
    inventory_id: UUID,
    current_user: User = Depends(require_admin),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Get a specific inventory item by ID (Admin access)."""
    try:
        item = await inventory_service.get_serialized(inventory_id)
        if not item:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND, message="Inventory item not found")
        return Response.success(data=item)
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch inventory item: {e}")


@router.get("/")
async def list(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    product_id: Optional[UUID] = Query(None),
    location_id: Optional[UUID] = Query(None),
    low_stock: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None, regex="^(updated_at|created_at|product_name|quantity|location_name)$"),
    sort_order: Optional[str] = Query(None, regex="^(asc|desc)$"),
    current_user: User = Depends(require_admin),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """List inventory items with filters (Admin access)."""
    try:
        items = await inventory_service.list(
            page=page,
            limit=limit,
            product_id=product_id,
            location_id=location_id,
            low_stock=low_stock,
            search=search,
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
            return Response.success(data=items.get("data", []), pagination=pagination)
        return Response.success(data=items)
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch inventory items: {e}")


@router.patch("/{inventory_id}")
async def patch(
    inventory_id: UUID,
    inventory_data: Update,
    current_user: User = Depends(require_admin),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Partially update an inventory item (Admin access)."""
    try:
        item = await inventory_service.update(inventory_id, inventory_data)
        return Response.success(data=item, message="Inventory item updated successfully")
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update inventory item: {e}")


@router.delete("/{inventory_id}")
async def delete(
    inventory_id: UUID,
    current_user: User = Depends(require_admin),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Delete an inventory item (Admin access)."""
    try:
        await inventory_service.delete(inventory_id)
        return Response.success(message="Inventory item deleted successfully")
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete inventory item: {e}")


# ==========================================================
# ADJUSTMENTS - 5 Standard APIs
# ==========================================================
@router.post("/adjustments")
async def create_adj(
    adjustment_data: AdjustmentCreate,
    current_user: User = Depends(require_admin),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Create a stock adjustment (Admin access)."""
    try:
        updated_inventory = await inventory_service.adjust_stock(adjustment_data, adjusted_by_user_id=current_user.id)
        return Response.success(data=updated_inventory, message="Stock adjusted successfully")
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to adjust stock: {e}")


@router.get("/adjustments/{adjustment_id}")
async def get_adj(
    adjustment_id: UUID,
    current_user: User = Depends(require_admin),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Get a specific stock adjustment by ID (Admin access)."""
    try:
        adjustment = await inventory_service.get_adjustment(adjustment_id)
        if not adjustment:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND, message="Stock adjustment not found")
        return Response.success(data=adjustment)
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch stock adjustment: {e}")


@router.get("/adjustments")
async def list_adj(
    current_user: User = Depends(require_admin),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """List all stock adjustments (Admin access)."""
    try:
        adjustments = await inventory_service.all_adjustments()
        return Response.success(data=adjustments)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch stock adjustments: {e}")


@router.delete("/adjustments/{adjustment_id}")
async def delete_adj(
    adjustment_id: UUID,
    current_user: User = Depends(require_admin),
    inventory_service: InventoryService = Depends(get_inventory_service)
):
    """Delete a stock adjustment (Admin access)."""
    try:
        deleted = await inventory_service.delete_adjustment(adjustment_id)
        if not deleted:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND, message="Stock adjustment not found")
        return Response.success(message="Stock adjustment deleted successfully")
    except APIException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete stock adjustment: {e}")