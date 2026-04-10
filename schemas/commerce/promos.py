from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from uuid import UUID


class Base(BaseModel):
    code: str = Field(..., min_length=1)
    description: Optional[str] = None
    discount_type: str = Field(...,
                               description="e.g., 'fixed', 'percentage', 'shipping'")
    value: float = Field(..., gt=0)
    minimum_order_amount: Optional[float] = None
    maximum_discount_amount: Optional[float] = None
    usage_limit: Optional[int] = None
    is_active: bool = True
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class Create(Base):
    pass


class Update(BaseModel):
    code: Optional[str] = None
    description: Optional[str] = None
    discount_type: Optional[str] = None
    value: Optional[float] = None
    minimum_order_amount: Optional[float] = None
    maximum_discount_amount: Optional[float] = None
    usage_limit: Optional[int] = None
    is_active: Optional[bool] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class InDB(Base):
    id: str
    used_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Validate promocode schemas
class ValidateRequest(BaseModel):
    code: str


class ValidateResponse(BaseModel):
    valid: bool
    code: str
    discount_type: Optional[str] = None
    value: Optional[float] = None
    minimum_order_amount: Optional[float] = None
    maximum_discount_amount: Optional[float] = None
    message: Optional[str] = None
