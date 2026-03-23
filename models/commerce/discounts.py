"""
Discount management models for subscription product management
"""
from sqlalchemy import Column, String, Boolean, DateTime, Float, Text, Integer, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from core.db import BaseModel, GUID
from datetime import datetime
from typing import Dict, Any


class Discount(BaseModel):
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
        {'extend_existing': True}
    )

    code = Column(String(50), unique=True, nullable=False)
    type = Column(String(20), nullable=False)  # PERCENTAGE, FIXED_AMOUNT, FREE_SHIPPING
    value = Column(Float, nullable=False)  # 10 for 10% or $10
    minimum_amount = Column(Float, nullable=True)
    maximum_discount = Column(Float, nullable=True)
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_until = Column(DateTime(timezone=True), nullable=False)
    usage_limit = Column(Integer, nullable=True)
    used_count = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    description = Column(Text, nullable=True)

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

    def is_valid(self) -> bool:
        """Check if discount is currently valid"""
        now = datetime.utcnow()
        return (
            self.is_active and
            self.valid_from <= now <= self.valid_until and
            (self.usage_limit is None or self.used_count < self.usage_limit)
        )

    def calculate_discount_amount(self, subtotal: float) -> float:
        """Calculate discount amount for given subtotal"""
        if not self.is_valid():
            return 0.0
        
        if self.minimum_amount and subtotal < self.minimum_amount:
            return 0.0
        
        if self.type == "PERCENTAGE":
            discount_amount = subtotal * (self.value / 100)
        elif self.type == "FIXED_AMOUNT":
            discount_amount = self.value
        elif self.type == "FREE_SHIPPING":
            return 0.0  # Handled separately in shipping calculation
        else:
            return 0.0
        
        # Apply maximum discount limit if set
        if self.maximum_discount and discount_amount > self.maximum_discount:
            discount_amount = self.maximum_discount
        
        # Ensure discount doesn't exceed subtotal
        return min(discount_amount, subtotal)


class SubscriptionDiscount(BaseModel):
    """Applied discounts tracking for subscriptions"""
    __tablename__ = "subscription_discounts"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_subscription_discounts_subscription_id', 'subscription_id'),
        Index('idx_subscription_discounts_discount_id', 'discount_id'),
        Index('idx_subscription_discounts_applied_at', 'applied_at'),
        # Composite indexes for common queries
        Index('idx_subscription_discounts_sub_discount', 'subscription_id', 'discount_id'),
        {'extend_existing': True}
    )

    subscription_id = Column(GUID(), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    discount_id = Column(GUID(), ForeignKey("discounts.id"), nullable=False)
    discount_amount = Column(Float, nullable=False)
    applied_at = Column(DateTime(timezone=True), server_default="NOW()", nullable=False)

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


class ProductRemovalAudit(BaseModel):
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
        {'extend_existing': True}
    )

    subscription_id = Column(GUID(), ForeignKey("subscriptions.id"), nullable=False)
    product_id = Column(GUID(), ForeignKey("products.id"), nullable=False)
    removed_by = Column(GUID(), ForeignKey("users.id"), nullable=False)
    removed_at = Column(DateTime(timezone=True), server_default="NOW()", nullable=False)
    reason = Column(Text, nullable=True)

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