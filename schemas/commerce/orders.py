from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime
from uuid import UUID

from models.commerce.orders import OrderStatus, PaymentStatus, FulfillmentStatus


class ItemCreate(BaseModel):
    variant_id: UUID
    quantity: int


class Address(BaseModel):
    street: str
    city: str
    state: str
    country: str
    post_code: str


class Checkout(BaseModel):
    shipping_address_id: UUID
    shipping_method_id: UUID  # Reverted back to UUID since we're using database shipping methods
    payment_method_id: UUID
    notes: Optional[str] = None
    currency: Optional[str] = "USD"  # User's detected currency
    country_code: Optional[str] = "US"  # User's detected country
    frontend_calculated_total: Optional[float] = None  # For validation
    idempotency_key: Optional[str] = None  # For duplicate prevention


class Create(BaseModel):
    items: List[ItemCreate]
    shipping_address: Address
    billing_address: Optional[Address] = None
    payment_method: str
    notes: Optional[str] = None


class Update(BaseModel):
    order_status: Optional[OrderStatus] = None
    payment_status: Optional[PaymentStatus] = None
    fulfillment_status: Optional[FulfillmentStatus] = None
    tracking_number: Optional[str] = None
    notes: Optional[str] = None


class ItemResponse(BaseModel):
    id: UUID
    variant_id: UUID
    quantity: int
    price_per_unit: float
    total_price: float
    variant: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class Response(BaseModel):
    id: UUID
    user_id: UUID
    order_status: OrderStatus
    payment_status: PaymentStatus
    fulfillment_status: FulfillmentStatus
    total_amount: float
    subtotal: Optional[float] = None
    tax_amount: Optional[float] = None
    shipping_cost: Optional[float] = None
    discount_amount: Optional[float] = None
    currency: str
    tracking_number: Optional[str]
    estimated_delivery: Optional[str]
    shipping_address: Optional[dict] = None
    billing_address: Optional[dict] = None
    items: List[ItemResponse]
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None
        }
    )


# Order Intent schemas
class IntentBase(BaseModel):
    user_id: UUID
    total_amount: float
    currency: str = "USD"
    status: str = "pending"


class IntentCreate(IntentBase):
    pass


class IntentUpdate(BaseModel):
    status: Optional[str] = None
    total_amount: Optional[float] = None


class IntentResponse(IntentBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# Order note schemas
class Note(BaseModel):
    note: str