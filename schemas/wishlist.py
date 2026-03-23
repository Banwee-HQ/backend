from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from schemas.product import ProductResponse, ProductVariantResponse


class WishlistItemBase(BaseModel):
    product_id: UUID
    variant_id: Optional[UUID] = None
    quantity: int = Field(1, gt=0)


class WishlistItemCreate(WishlistItemBase):
    pass


class WishlistItemResponse(WishlistItemBase):
    id: UUID
    wishlist_id: UUID
    added_at: str = Field(..., description="ISO format datetime string")
    product: Optional[ProductResponse] = None
    variant: Optional[ProductVariantResponse] = None

    model_config = ConfigDict(from_attributes=True)


class WishlistBase(BaseModel):
    name: Optional[str] = None
    is_default: bool = False


class WishlistCreate(WishlistBase):
    pass


class WishlistUpdate(WishlistBase):
    name: Optional[str] = None
    is_default: Optional[bool] = None


class WishlistResponse(WishlistBase):
    id: UUID
    user_id: UUID
    created_at: str = Field(..., description="ISO format datetime string")
    updated_at: Optional[str] = Field(None, description="ISO format datetime string")
    items: List[WishlistItemResponse] = []

    model_config = ConfigDict(from_attributes=True)
