from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from uuid import UUID
from datetime import datetime


# --- WarehouseLocation Schemas ---
class WarehouseLocationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    address: Optional[str] = None
    description: Optional[str] = None


class WarehouseLocationCreate(WarehouseLocationBase):
    pass


class WarehouseLocationUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    description: Optional[str] = None


class WarehouseLocationResponse(WarehouseLocationBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# --- Inventory Schemas ---
class InventoryBase(BaseModel):
    variant_id: UUID
    location_id: UUID
    quantity: int = Field(default=0, ge=0)
    low_stock_threshold: int = Field(default=10, ge=0)


class InventoryCreate(InventoryBase):
    pass


class InventoryUpdate(BaseModel):
    location_id: Optional[UUID] = None
    location_name: Optional[str] = None
    quantity: Optional[int] = Field(default=None, ge=0)
    low_stock_threshold: Optional[int] = Field(default=None, ge=0)


class InventoryResponse(InventoryBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
    quantity_available: Optional[int] = None
    reorder_point: Optional[int] = None
    inventory_status: Optional[str] = None
    last_restocked_at: Optional[datetime] = None
    last_sold_at: Optional[datetime] = None
    version: Optional[int] = None
    location: Optional[WarehouseLocationResponse] = None

    model_config = ConfigDict(from_attributes=True)


# --- StockAdjustment Schemas ---
class StockAdjustmentBase(BaseModel):
    inventory_id: UUID
    quantity_change: int
    reason: str = Field(..., min_length=1, max_length=255)
    adjusted_by_user_id: Optional[UUID] = None
    notes: Optional[str] = None


class StockAdjustmentCreate(BaseModel):
    variant_id: Optional[UUID] = None
    location_id: Optional[UUID] = None
    quantity_change: int
    reason: str = Field(..., min_length=1, max_length=255)
    notes: Optional[str] = None


class StockAdjustmentResponse(StockAdjustmentBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)