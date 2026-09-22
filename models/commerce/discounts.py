"""
Discount management models for subscription product management
"""
from sqlalchemy import String, Boolean, DateTime, Numeric, Text, Integer, func, Index, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from core.db import Base, GUID, UTCDateTime
from core.utils.uuid_utils import uuid7
from datetime import datetime
from typing import Dict, Any, Optional
import uuid
from enum import Enum


class DiscountType(str, Enum):
    """Discount type options"""
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"
    FREE_SHIPPING = "free_shipping"


class Discount(Base):
    """Discount codes and promotional offers"""
    __tablename__ = "discounts"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_discounts_code', 'code'),
        Index('idx_discounts_active', 'is_active'),
        Index('idx_discounts_type', 'type'),
        Index('idx_discounts_valid_from', 'valid_from'),
        Index('idx_discounts_valid_until', 'valid_until'),
        Index('idx_discounts_usage_limit', 'usage_limit'),
        Index('idx_discounts_used_count', 'used_count'),
        # Composite indexes for common queries
        Index('idx_discounts_active_valid', 'is_active', 'valid_from', 'valid_until'),
        Index('idx_discounts_code_active', 'code', 'is_active'),
        {'schema': 'commerce'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), onupdate=func.now(), nullable=True)

    code: Mapped[str] = mapped_column(String(50), unique=True)
    type: Mapped[DiscountType] = mapped_column(String(20))
    value: Mapped[float] = mapped_column(Numeric(10, 2))  # 10 for 10% or $10
    minimum_amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    maximum_discount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    valid_from: Mapped[datetime] = mapped_column(UTCDateTime())
    valid_until: Mapped[datetime] = mapped_column(UTCDateTime())
    usage_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    subscription_discounts = relationship("SubscriptionDiscount", back_populates="discount", lazy="select")

    def to_dict(self) -> Dict[str, Any]:
        """Convert discount to dictionary for API responses"""
        return {
            "id": str(self.id),
            "code": self.code,
            "type": self.type,
            "value": self.value,
            "minimum_amount": self.minimum_amount,
            "maximum_discount": self.maximum_discount,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "usage_limit": self.usage_limit,
            "used_count": self.used_count,
            "is_active": self.is_active,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

class SubscriptionDiscount(Base):
    """Applied discounts tracking for subscriptions"""
    __tablename__ = "subscription_discounts"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_subscription_discounts_subscription_id', 'subscription_id'),
        Index('idx_subscription_discounts_discount_id', 'discount_id'),
        Index('idx_subscription_discounts_applied_at', 'applied_at'),
        # Composite indexes for common queries
        Index('idx_subscription_discounts_sub_discount', 'subscription_id', 'discount_id'),
        {'schema': 'commerce'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), onupdate=func.now(), nullable=True)

    subscription_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("commerce.subscriptions.id", ondelete="CASCADE"))
    discount_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("commerce.discounts.id"))
    discount_amount: Mapped[float] = mapped_column(Numeric(10, 2))
    applied_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())

    # Relationships
    subscription = relationship("Subscription", back_populates="applied_discounts", lazy="select")
    discount = relationship("Discount", back_populates="subscription_discounts", lazy="select")

    def to_dict(self) -> Dict[str, Any]:
        """Convert subscription discount to dictionary for API responses"""
        return {
            "id": str(self.id),
            "subscription_id": str(self.subscription_id),
            "discount_id": str(self.discount_id),
            "discount_amount": self.discount_amount,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "discount": self.discount.to_dict() if self.discount else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ProductRemovalAudit(Base):
    """Audit trail for product removals from subscriptions"""
    __tablename__ = "product_removal_audit"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_product_removal_audit_subscription_id', 'subscription_id'),
        Index('idx_product_removal_audit_product_id', 'product_id'),
        Index('idx_product_removal_audit_removed_by', 'removed_by'),
        Index('idx_product_removal_audit_removed_at', 'removed_at'),
        # Composite indexes for common queries
        Index('idx_product_removal_audit_sub_product', 'subscription_id', 'product_id'),
        Index('idx_product_removal_audit_user_date', 'removed_by', 'removed_at'),
        {'schema': 'commerce'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), onupdate=func.now(), nullable=True)

    subscription_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("commerce.subscriptions.id"))
    product_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("catalog.products.id"))
    removed_by: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("accounts.users.id"))
    removed_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    subscription = relationship("Subscription", lazy="select")
    product = relationship("Product", lazy="select")
    user = relationship("User", lazy="select")

    def to_dict(self) -> Dict[str, Any]:
        """Convert product removal audit to dictionary for API responses"""
        return {
            "id": str(self.id),
            "subscription_id": str(self.subscription_id),
            "product_id": str(self.product_id),
            "removed_by": str(self.removed_by),
            "removed_at": self.removed_at.isoformat() if self.removed_at else None,
            "reason": self.reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }