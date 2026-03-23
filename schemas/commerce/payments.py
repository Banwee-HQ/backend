from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime


class PaymentMethodBase(BaseModel):
    type: str = Field(..., description="Type of payment method (e.g., credit_card, paypal)")
    provider: Optional[str] = Field(None, description="Payment provider (e.g., Visa, PayPal)")
    last_four: Optional[str] = Field(None, max_length=4, description="Last four digits of the card number")
    expiry_month: Optional[int] = Field(None, ge=1, le=12, description="Card expiry month")
    expiry_year: Optional[int] = Field(None, ge=2000, description="Card expiry year")
    is_default: bool = Field(False, description="Whether this is the default payment method")


class PaymentMethodCreate(BaseModel):
    stripe_payment_method_id: Optional[str] = Field(None, description="Stripe payment method ID for modern API")
    stripe_token: Optional[str] = Field(None, description="Stripe token for legacy API (deprecated)")
    type: str = Field(..., description="Type of payment method (e.g., card)")
    provider: Optional[str] = Field(None, description="Payment provider (e.g., visa, mastercard)")
    last_four: Optional[str] = Field(None, max_length=4, description="Last four digits of the card number")
    expiry_month: Optional[int] = Field(None, ge=1, le=12, description="Card expiry month")
    expiry_year: Optional[int] = Field(None, ge=2000, description="Card expiry year")
    is_default: bool = Field(False, description="Whether to set this as the default payment method")


class PaymentMethodUpdate(BaseModel):
    is_default: Optional[bool] = None
    meta_data: Optional[dict] = None


class PaymentMethodResponse(PaymentMethodBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# Payment Intent schemas
class PaymentIntentBase(BaseModel):
    amount: float
    currency: str = "USD"
    status: str = "pending"
    payment_method_id: Optional[UUID] = None


class PaymentIntentCreate(BaseModel):
    amount: float
    currency: str = "USD"
    order_id: Optional[UUID] = None


class PaymentIntentUpdate(BaseModel):
    status: Optional[str] = None
    amount: Optional[float] = None


class PaymentIntentResponse(PaymentIntentBase):
    id: UUID
    user_id: UUID
    order_id: Optional[UUID] = None
    stripe_payment_intent_id: Optional[str] = None
    client_secret: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# Transaction schemas
class TransactionBase(BaseModel):
    amount: float
    currency: str = "USD"
    type: str  # "payment", "refund", "chargeback"
    status: str = "pending"
    description: Optional[str] = None


class TransactionCreate(TransactionBase):
    user_id: UUID
    payment_intent_id: Optional[UUID] = None
    order_id: Optional[UUID] = None


class TransactionUpdate(BaseModel):
    status: Optional[str] = None
    description: Optional[str] = None


class TransactionResponse(TransactionBase):
    id: UUID
    user_id: UUID
    payment_intent_id: Optional[UUID] = None
    order_id: Optional[UUID] = None
    stripe_transaction_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)