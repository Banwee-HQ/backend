from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from uuid import UUID


class MethodBase(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    price: float = Field(..., ge=0)
    estimated_days: int = Field(..., ge=1)
    is_active: bool = True
    
    # Simple metadata
    carrier: Optional[str] = Field(None, description="Shipping carrier name")
    tracking_url_template: Optional[str] = Field(None, description="URL template for tracking")


class MethodCreate(MethodBase):
    pass


class MethodUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    estimated_days: Optional[int] = Field(None, ge=1)
    is_active: Optional[bool] = None
    
    # Simple metadata
    carrier: Optional[str] = None
    tracking_url_template: Optional[str] = None


class MethodInDB(MethodBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# Shipping calculation schema
class Calculate(BaseModel):
    order_amount: Optional[float] = None
    shipping_method_id: Optional[UUID] = None
    destination_country: Optional[str] = "US"
    address_id: Optional[UUID] = None
    items: Optional[list] = None
