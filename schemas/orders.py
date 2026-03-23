from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime
from uuid import UUID


class OrderItemCreate(BaseModel):
    variant_id: UUID
    quantity: int


class AddressCreate(BaseModel):
    street: str
    city: str
    state: str
    country: str
    post_code: str


class CheckoutRequest(BaseModel):
    shipping_address_id: UUID
    shipping_method_id: UUID  # Reverted back to UUID since we're using database shipping methods
    payment_method_id: UUID
    notes: Optional[str] = None
    currency: Optional[str] = "USD"  # User's detected currency
    country_code: Optional[str] = "US"  # User's detected country
    frontend_calculated_total: Optional[float] = None  # For validation
    idempotency_key: Optional[str] = None  # For duplicate prevention


class OrderCreate(BaseModel):
    items: List[OrderItemCreate]
    shipping_address: AddressCreate
    billing_address: Optional[AddressCreate] = None
    payment_method: str
    notes: Optional[str] = None


class OrderUpdate(BaseModel):
    status: Optional[str] = None
    tracking_number: Optional[str] = None
    notes: Optional[str] = None


class OrderItemResponse(BaseModel):
    id: UUID
    variant_id: UUID
    quantity: int
    price_per_unit: float
    total_price: float
    variant: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(BaseModel):
    id: UUID
    user_id: UUID
    status: str
    total_amount: float
    subtotal: Optional[float] = None
    tax_amount: Optional[float] = None
    shipping_amount: Optional[float] = None
    discount_amount: Optional[float] = None
    currency: str
    tracking_number: Optional[str]
    estimated_delivery: Optional[str]
    shipping_address: Optional[dict] = None
    billing_address: Optional[dict] = None
    items: List[OrderItemResponse]
    created_at: str = Field(..., description="ISO format datetime string")

    model_config = ConfigDict(from_attributes=True, json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


# Order Intent schemas
class OrderIntentBase(BaseModel):
    user_id: UUID
    total_amount: float
    currency: str = "USD"
    status: str = "pending"


class OrderIntentCreate(OrderIntentBase):
    pass


class OrderIntentUpdate(BaseModel):
    status: Optional[str] = None
    total_amount: Optional[float] = None


class OrderIntentResponse(OrderIntentBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)