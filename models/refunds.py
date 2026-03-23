"""
Refund models for painless refund processing
Includes: Refund, RefundItem, RefundReason
"""
from sqlalchemy import Column, String, ForeignKey, Float, Text, Integer, DateTime, Boolean, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from core.db import BaseModel, GUID, Index
from enum import Enum
from typing import Dict, Any
from datetime import datetime, timezone


class RefundStatus(Enum):
    """Refund status enumeration"""
    REQUESTED = "requested"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RefundReason(Enum):
    """Refund reason enumeration"""
    DEFECTIVE_PRODUCT = "defective_product"
    WRONG_ITEM = "wrong_item"
    NOT_AS_DESCRIBED = "not_as_described"
    DAMAGED_IN_SHIPPING = "damaged_in_shipping"
    CHANGED_MIND = "changed_mind"
    DUPLICATE_ORDER = "duplicate_order"
    UNAUTHORIZED_PURCHASE = "unauthorized_purchase"
    LATE_DELIVERY = "late_delivery"
    MISSING_PARTS = "missing_parts"
    SIZE_ISSUE = "size_issue"
    QUALITY_ISSUE = "quality_issue"
    OTHER = "other"


class RefundType(Enum):
    """Refund type enumeration"""
    FULL_REFUND = "full_refund"
    PARTIAL_REFUND = "partial_refund"
    STORE_CREDIT = "store_credit"
    EXCHANGE = "exchange"


class Refund(BaseModel):
    """Refund model for tracking refund requests and processing"""
    __tablename__ = "refunds"
    __table_args__ = (
        # Indexes for efficient queries
        Index('idx_refunds_order_id', 'order_id'),
        Index('idx_refunds_user_id', 'user_id'),
        Index('idx_refunds_status', 'status'),
        Index('idx_refunds_type', 'refund_type'),
        Index('idx_refunds_created_at', 'created_at'),
        Index('idx_refunds_stripe_refund_id', 'stripe_refund_id'),
        # Composite indexes for common queries
        Index('idx_refunds_user_status', 'user_id', 'status'),
        Index('idx_refunds_order_status', 'order_id', 'status'),
        Index('idx_refunds_status_created', 'status', 'created_at'),
        {'extend_existing': True}
    )

    # References
    order_id = Column(GUID(), ForeignKey("orders.id"), nullable=False)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    
    # Refund details
    refund_number = Column(String(50), unique=True, nullable=False)  # REF-XXXXXXXX
    status = Column(SQLEnum(RefundStatus), default=RefundStatus.REQUESTED, nullable=False)
    refund_type = Column(SQLEnum(RefundType), default=RefundType.FULL_REFUND, nullable=False)
    reason = Column(SQLEnum(RefundReason), nullable=False)
    
    # Financial information
    requested_amount = Column(Float, nullable=False)
    approved_amount = Column(Float, nullable=True)
    processed_amount = Column(Float, nullable=True)
    currency = Column(String(3), default="USD", nullable=False)
    
    # Stripe integration
    stripe_refund_id = Column(String(255), nullable=True, unique=True)
    stripe_status = Column(String(50), nullable=True)
    
    # Customer information
    customer_reason = Column(Text, nullable=True)  # Customer's explanation
    customer_notes = Column(Text, nullable=True)   # Additional customer notes
    
    # Admin information
    admin_notes = Column(Text, nullable=True)      # Internal admin notes
    reviewed_by = Column(GUID(), ForeignKey("users.id"), nullable=True)  # Admin who reviewed
    processed_by = Column(GUID(), ForeignKey("users.id"), nullable=True) # Admin who processed
    
    # Timestamps
    requested_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Automation flags
    auto_approved = Column(Boolean, default=False)  # Was this auto-approved?
    requires_return = Column(Boolean, default=True) # Does customer need to return items?
    return_shipping_paid = Column(Boolean, default=False) # Did we pay for return shipping?
    
    # Metadata for additional information
    refund_metadata = Column(JSONB, default=dict)  # Store additional refund data
    
    # Relationships
    order = relationship("Order", back_populates="refunds")
    user = relationship("User", foreign_keys=[user_id], back_populates="created_refunds")
    reviewer = relationship("User", foreign_keys=[reviewed_by], back_populates="reviewed_refunds")
    processor = relationship("User", foreign_keys=[processed_by], back_populates="processed_refunds")
    refund_items = relationship("RefundItem", back_populates="refund", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "order_id": str(self.order_id),
            "user_id": str(self.user_id),
            "refund_number": self.refund_number,
            "status": self.status.value if self.status else None,
            "refund_type": self.refund_type.value if self.refund_type else None,
            "reason": self.reason.value if self.reason else None,
            "requested_amount": self.requested_amount,
            "approved_amount": self.approved_amount,
            "processed_amount": self.processed_amount,
            "currency": self.currency,
            "stripe_refund_id": self.stripe_refund_id,
            "stripe_status": self.stripe_status,
            "customer_reason": self.customer_reason,
            "customer_notes": self.customer_notes,
            "admin_notes": self.admin_notes,
            "auto_approved": self.auto_approved,
            "requires_return": self.requires_return,
            "return_shipping_paid": self.return_shipping_paid,
            "requested_at": self.requested_at.isoformat() if self.requested_at else None,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "refund_metadata": self.refund_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @property
    def is_eligible_for_auto_approval(self) -> bool:
        """Check if refund is eligible for automatic approval"""
        # Auto-approve if:
        # 1. Requested within 30 days of order
        # 2. Full refund for defective/wrong item
        # 3. Amount is reasonable (< $500)
        if not self.order or not self.order.created_at:
            return False
            
        days_since_order = (datetime.now(timezone.utc) - self.order.created_at).days
        
        auto_approval_reasons = [
            RefundReason.DEFECTIVE_PRODUCT,
            RefundReason.WRONG_ITEM,
            RefundReason.DAMAGED_IN_SHIPPING,
            RefundReason.MISSING_PARTS
        ]
        
        return (
            days_since_order <= 30 and
            self.reason in auto_approval_reasons and
            self.requested_amount <= 500.00 and
            self.refund_type == RefundType.FULL_REFUND
        )


class RefundItem(BaseModel):
    """Individual items being refunded"""
    __tablename__ = "refund_items"
    __table_args__ = (
        Index('idx_refund_items_refund_id', 'refund_id'),
        Index('idx_refund_items_order_item_id', 'order_item_id'),
        {'extend_existing': True}
    )

    # References
    refund_id = Column(GUID(), ForeignKey("refunds.id"), nullable=False)
    order_item_id = Column(GUID(), ForeignKey("order_items.id"), nullable=False)
    
    # Item details
    quantity_to_refund = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    total_refund_amount = Column(Float, nullable=False)
    
    # Item condition
    condition_notes = Column(Text, nullable=True)  # Customer notes about item condition
    
    # Relationships
    refund = relationship("Refund", back_populates="refund_items")
    order_item = relationship("OrderItem")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "refund_id": str(self.refund_id),
            "order_item_id": str(self.order_item_id),
            "quantity_to_refund": self.quantity_to_refund,
            "unit_price": self.unit_price,
            "total_refund_amount": self.total_refund_amount,
            "condition_notes": self.condition_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }