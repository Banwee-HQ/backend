from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime


class TransactionBase(BaseModel):
    user_id: UUID
    order_id: Optional[UUID] = None
    stripe_payment_intent_id: str
    amount: float
    currency: str
    status: str = Field(
        "pending", description="Status of the transaction (e.g., pending, succeeded, failed)")
    transaction_type: Optional[str] = Field(
        None, description="Type of transaction (e.g., payment, refund, payout)")
    description: Optional[str] = None


class TransactionCreate(TransactionBase):
    pass


class TransactionUpdate(BaseModel):
    status: Optional[str] = None
    description: Optional[str] = None


class TransactionResponse(TransactionBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
