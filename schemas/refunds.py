"""
Refund schemas for API requests and responses
"""
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from enum import Enum

from models.refunds import RefundStatus, RefundReason, RefundType


class RefundItemRequest(BaseModel):
    """Request schema for individual refund items"""
    order_item_id: UUID = Field(..., description="ID of the order item to refund")
    quantity: int = Field(..., ge=1, description="Quantity to refund")
    condition_notes: Optional[str] = Field(None, max_length=500, description="Notes about item condition")


class RefundRequest(BaseModel):
    """Request schema for creating a refund"""
    refund_type: RefundType = Field(RefundType.FULL_REFUND, description="Type of refund requested")
    reason: RefundReason = Field(..., description="Reason for refund")
    customer_reason: Optional[str] = Field(None, max_length=1000, description="Customer's detailed explanation")
    customer_notes: Optional[str] = Field(None, max_length=1000, description="Additional customer notes")
    items: List[RefundItemRequest] = Field(..., min_items=1, description="Items to refund")

    @validator('items')
    def validate_items(cls, v):
        if not v:
            raise ValueError("At least one item must be specified for refund")
        return v


class RefundItemResponse(BaseModel):
    """Response schema for refund items"""
    order_item_id: UUID
    quantity: int
    amount: float
    condition_notes: Optional[str]


class RefundTimelineItem(BaseModel):
    """Timeline item for refund progress"""
    status: str
    title: str
    description: str
    timestamp: Optional[datetime]
    completed: bool


class RefundResponse(BaseModel):
    """Response schema for refund details"""
    id: UUID
    order_id: UUID
    refund_number: str
    status: RefundStatus
    refund_type: RefundType
    reason: RefundReason
    requested_amount: float
    approved_amount: Optional[float]
    processed_amount: Optional[float]
    currency: str
    customer_reason: Optional[str]
    customer_notes: Optional[str]
    auto_approved: bool
    requires_return: bool
    return_shipping_paid: bool
    requested_at: datetime
    approved_at: Optional[datetime]
    processed_at: Optional[datetime]
    completed_at: Optional[datetime]
    items: List[RefundItemResponse]
    timeline: List[RefundTimelineItem]

    class Config:
        from_attributes = True


class RefundListResponse(BaseModel):
    """Response schema for refund list"""
    refunds: List[RefundResponse]
    total: int
    page: int
    limit: int


class RefundEligibilityResponse(BaseModel):
    """Response schema for refund eligibility check"""
    eligible: bool
    reason: Optional[str]
    max_refund_amount: Optional[float]
    refund_window_days: int
    order_age_days: int


class RefundStatsResponse(BaseModel):
    """Response schema for refund statistics"""
    total_refunds: int
    total_amount: float
    auto_approved_count: int
    pending_count: int
    completed_count: int
    average_processing_time_hours: Optional[float]