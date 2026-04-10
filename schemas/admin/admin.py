"""
Admin schemas
"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from uuid import UUID


# Order admin schemas
class ShipOrder(BaseModel):
    tracking_number: str
    carrier_name: str


class UpdateOrderStatus(BaseModel):
    status: str
    tracking_number: Optional[str] = None
    carrier_name: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None


class OrderPatch(BaseModel):
    """Request model for partial order updates via PATCH."""
    status: Optional[str] = None
    tracking_number: Optional[str] = None
    carrier_name: Optional[str] = None
    notes: Optional[str] = None
    admin_notes: Optional[str] = None


# Refund admin schemas
class UpdateRefundStatus(BaseModel):
    status: str
    admin_notes: Optional[str] = None


# User admin schemas
class UserUpdate(BaseModel):
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


# Product admin schemas
class ProductPatch(BaseModel):
    """Request model for partial product updates via PATCH."""
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    compare_at_price: Optional[float] = None
    category: Optional[str] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None
    tags: Optional[list] = None
    seo_title: Optional[str] = None


# Tax rate admin schemas
class TaxCreate(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2, description="ISO 3166-1 alpha-2 country code")
    country_name: str = Field(..., min_length=1, max_length=100)
    province_code: Optional[str] = Field(None, max_length=10, description="State/Province code")
    province_name: Optional[str] = Field(None, max_length=100)
    tax_rate: float = Field(..., ge=0, le=1, description="Tax rate as decimal (e.g., 0.0725 for 7.25%)")
    tax_name: Optional[str] = Field(None, max_length=50, description="e.g., GST, VAT, Sales Tax")
    is_active: bool = True


class TaxUpdate(BaseModel):
    country_name: Optional[str] = Field(None, min_length=1, max_length=100)
    province_name: Optional[str] = Field(None, max_length=100)
    tax_rate: Optional[float] = Field(None, ge=0, le=1)
    tax_name: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None


class TaxResponse(BaseModel):
    id: UUID
    country_code: str
    country_name: str
    province_code: Optional[str]
    province_name: Optional[str]
    tax_rate: float
    tax_percentage: float  # Computed: tax_rate * 100
    tax_name: Optional[str]
    is_active: bool
    created_at: str
    updated_at: Optional[str]

    class Config:
        from_attributes = True
