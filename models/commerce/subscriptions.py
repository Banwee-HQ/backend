"""
Consolidated subscription models
Includes: Subscription and related subscription models
Optimized for PostgreSQL with partial indexes for active subscriptions and products
"""
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Numeric, Table, JSON, Text, Integer, Date, func, Index, Column
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from core.db import Base, GUID
from core.utils.uuid_utils import uuid7
from typing import Dict, Any, Optional
from datetime import datetime
import uuid
from enum import Enum


class SubscriptionStatus(str, Enum):
    """Subscription status types"""
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    PAST_DUE = "past_due"
    UNPAID = "unpaid"
    INCOMPLETE = "incomplete"


class DeliveryType(str, Enum):
    """Delivery type options"""
    STANDARD = "standard"
    EXPRESS = "express"
    OVERNIGHT = "overnight"


class BillingCycle(str, Enum):
    """Billing cycle options"""
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


# --- Association model: Subscription <-> ProductVariant ---
class SubscriptionProductAssociation(Base):
    """Association table for Subscription and ProductVariant many-to-many relationship"""
    __tablename__ = "subscription_product_association"
    __table_args__ = (
        Index('idx_sub_product_association_variant', 'product_variant_id'),
        Index('idx_sub_product_association_subscription', 'subscription_id'),
        {'schema': 'commerce'}
    )

    subscription_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("commerce.subscriptions.id", ondelete="CASCADE"), primary_key=True)
    product_variant_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("catalog.product_variants.id"), primary_key=True)

    # Relationships
    subscription = relationship("Subscription", backref="variant_associations")
    product_variant = relationship("ProductVariant", backref="subscription_associations")


class SubscriptionProduct(Base):
    """Tracks individual products within subscriptions with removal tracking"""
    __tablename__ = "subscription_products"
    __table_args__ = (
        # Basic indexes
        Index('idx_subscription_products_subscription_id', 'subscription_id'),
        Index('idx_subscription_products_product_id', 'product_id'),
        Index('idx_subscription_products_removed_by', 'removed_by'),
        # Composite indexes
        Index('idx_subscription_products_sub_product', 'subscription_id', 'product_id'),
        # Partial index for active products only (removed_at IS NULL)
        Index('idx_subscription_products_active', 'subscription_id', 'product_id', unique=False,
              postgresql_where=Column('removed_at').is_(None)),
        {'schema': 'commerce'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    subscription_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("commerce.subscriptions.id", ondelete="CASCADE"))
    product_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("catalog.products.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2))
    total_price: Mapped[float] = mapped_column(Numeric(10, 2))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="NOW()")

    # Removal tracking
    removed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("accounts.users.id"), nullable=True)

    # Relationships
    subscription = relationship("Subscription", back_populates="subscription_products", lazy="select")
    product = relationship("Product", lazy="select")
    removed_by_user = relationship("User", lazy="select")

    @property
    def is_active(self) -> bool:
        return self.removed_at is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "subscription_id": str(self.subscription_id),
            "product_id": str(self.product_id),
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "total_price": self.total_price,
            "added_at": self.added_at.isoformat() if self.added_at else None,
            "removed_at": self.removed_at.isoformat() if self.removed_at else None,
            "removed_by": str(self.removed_by) if self.removed_by else None,
            "is_active": self.is_active,
            "product": self.product.to_dict() if self.product else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Subscription(Base):
    """Robust subscription model with at-creation and current pricing for e-commerce"""
    __tablename__ = "subscriptions"
    __table_args__ = (
        # Single-column indexes
        Index('idx_subscriptions_user_id', 'user_id'),
        Index('idx_subscriptions_status', 'status'),
        Index('idx_subscriptions_next_billing_date', 'next_billing_date'),
        Index('idx_subscriptions_delivery_address', 'delivery_address_id'),
        # Composite indexes
        Index('idx_subscriptions_user_status', 'user_id', 'status'),
        Index('idx_subscriptions_status_next_billing', 'status', 'next_billing_date'),
        # Partial index for active subscriptions
        Index('idx_subscriptions_active', 'user_id', 'status', unique=False,
              postgresql_where=Column('status') == 'active'),
        {'schema': 'commerce'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # --- Core fields ---
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("accounts.users.id"))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[SubscriptionStatus] = mapped_column(String(50), default=SubscriptionStatus.ACTIVE)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    billing_cycle: Mapped[BillingCycle] = mapped_column(String(20), default=BillingCycle.MONTHLY)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True)
    current_period_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_billing_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    pause_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_payment_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payment_retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_payment_attempt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Payment info ---
    payment_gateway: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # --- Delivery info ---
    delivery_type: Mapped[Optional[DeliveryType]] = mapped_column(String(50), default=DeliveryType.STANDARD)
    delivery_address_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("accounts.addresses.id"), nullable=True)

    # --- Pricing at creation ---
    price_at_creation: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    variant_prices_at_creation: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    shipping_amount_at_creation: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    tax_amount_at_creation: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    tax_rate_at_creation: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)

    # --- Current/dynamic pricing ---
    current_variant_prices: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    current_shipping_amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    current_tax_amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    current_tax_rate: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)

    # --- Products & variants ---
    variant_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    subscription_products = relationship("SubscriptionProduct", back_populates="subscription", lazy="select")
    products = relationship(
        "ProductVariant",
        secondary="subscription_product_association",
        backref="subscriptions_containing",
        lazy="selectin"
    )

    # --- Metadata ---
    subscription_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # --- Discount fields ---
    discount_id = Column(GUID(), ForeignKey("commerce.promocodes.id"), nullable=True)
    discount_type = Column(String(20), nullable=True)  # "percentage" or "fixed"
    discount_value = Column(Numeric(10, 2), nullable=True)
    discount_code = Column(String(50), nullable=True)

    # --- Relationships ---
    user = relationship("User", back_populates="subscriptions")
    delivery_address = relationship("Address", foreign_keys=[delivery_address_id])
    orders = relationship("Order", back_populates="subscription", lazy="select")
    applied_discounts = relationship("SubscriptionDiscount", back_populates="subscription", lazy="select")
    variant_tracking_entries = relationship("VariantTrackingEntry", back_populates="subscription", lazy="select")

    def to_dict(self, include_products=False) -> Dict[str, Any]:
        data = {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "name": self.name,
            "status": self.status,
            "currency": self.currency,
            "billing_cycle": self.billing_cycle,
            "auto_renew": self.auto_renew,
            "current_period_start": self.current_period_start.isoformat() if self.current_period_start else None,
            "current_period_end": self.current_period_end.isoformat() if self.current_period_end else None,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "next_billing_date": self.next_billing_date.isoformat() if self.next_billing_date else None,
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
            "pause_reason": self.pause_reason,
            "last_payment_error": self.last_payment_error,
            "variant_ids": self.variant_ids or [],
            "subscription_metadata": self.subscription_metadata or {},
            # At-creation prices
            "price_at_creation": self.price_at_creation,
            "variant_prices_at_creation": self.variant_prices_at_creation or [],
            "shipping_amount_at_creation": self.shipping_amount_at_creation,
            "tax_amount_at_creation": self.tax_amount_at_creation,
            "tax_rate_at_creation": self.tax_rate_at_creation,
            # Current/dynamic prices
            "current_variant_prices": self.current_variant_prices or [],
            "current_shipping_amount": self.current_shipping_amount,
            "current_tax_amount": self.current_tax_amount,
            "current_tax_rate": self.current_tax_rate,
            # Discount info
            "discount": {
                "type": self.discount_type,
                "value": self.discount_value,
                "code": self.discount_code
            } if self.discount_type else None,
            # Payment info
            "payment_gateway": self.payment_gateway,
            "payment_reference": self.payment_reference,
            "delivery_type": self.delivery_type,
            "delivery_address_id": str(self.delivery_address_id) if self.delivery_address_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_products and self.products:
            products_dict = {}
            for variant in self.products:
                try:
                    if hasattr(variant, 'product') and variant.product:
                        pid = str(variant.product.id)
                        if pid not in products_dict:
                            image_url = None
                            if hasattr(variant, 'images') and variant.images:
                                primary_img = next(
                                    (img for img in variant.images if getattr(img, 'is_primary', False)),
                                    variant.images[0]
                                )
                                image_url = getattr(primary_img, 'url', None)

                            products_dict[pid] = {
                                "id": pid,
                                "name": variant.product.name,
                                "price": float(getattr(variant, 'base_price', 0)),
                                "current_price": float(getattr(variant, 'current_price', getattr(variant, 'base_price', 0))),
                                "image": image_url,
                                "variant_id": str(variant.id)
                            }
                except Exception:
                    continue

            data["products"] = list(products_dict.values())

        return data


class SubscriptionCostHistory(Base):
    """Historical record of subscription cost changes"""
    __tablename__ = "subscription_cost_history"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_subscription_cost_history_subscription_id', 'subscription_id'),
        Index('idx_subscription_cost_history_change_reason', 'change_reason'),
        Index('idx_subscription_cost_history_effective_date', 'effective_date'),
        Index('idx_subscription_cost_history_changed_by', 'changed_by'),
        Index('idx_subscription_cost_history_created_at', 'created_at'),
        # Composite indexes for common queries
        Index('idx_subscription_cost_history_sub_effective', 'subscription_id', 'effective_date'),
        {'schema': 'commerce'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    subscription_id: Mapped[uuid.UUID] = mapped_column(GUID())

    # Old cost breakdown (JSON)
    old_cost_breakdown: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # New cost breakdown (JSON)
    new_cost_breakdown: Mapped[dict] = mapped_column(JSON)

    # Reason for cost change
    change_reason: Mapped[str] = mapped_column(String(100))  # "admin_percentage_change", "variant_price_change", etc.

    # When the change becomes effective
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Admin user who triggered the change (if applicable)
    changed_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)

    # Additional metadata
    pricing_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert cost history to dictionary"""
        return {
            "id": str(self.id),
            "subscription_id": str(self.subscription_id),
            "old_cost_breakdown": self.old_cost_breakdown,
            "new_cost_breakdown": self.new_cost_breakdown,
            "change_reason": self.change_reason,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "changed_by": str(self.changed_by) if self.changed_by else None,
            "metadata": self.pricing_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SubscriptionAnalytics(Base):
    """Daily subscription analytics and metrics"""
    __tablename__ = "subscription_analytics"

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Date for this analytics record
    date: Mapped[Date] = mapped_column(Date)

    # Subscription metrics
    total_active_subscriptions: Mapped[int] = mapped_column(Integer, default=0)
    new_subscriptions: Mapped[int] = mapped_column(Integer, default=0)
    canceled_subscriptions: Mapped[int] = mapped_column(Integer, default=0)
    paused_subscriptions: Mapped[int] = mapped_column(Integer, default=0)
    resumed_subscriptions: Mapped[int] = mapped_column(Integer, default=0)

    # Revenue metrics
    total_revenue: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0)
    average_subscription_value: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0)
    monthly_recurring_revenue: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0)

    # Performance metrics
    churn_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0)
    conversion_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0)
    retention_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0)

    # Currency
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Breakdown by subscription type/plan (JSON)
    plan_breakdown: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Breakdown by delivery type (JSON)
    delivery_breakdown: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Geographic breakdown (JSON)
    geographic_breakdown: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Additional metrics (JSON)
    additional_metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        {'schema': 'commerce'},
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert subscription analytics to dictionary"""
        return {
            "id": str(self.id),
            "date": self.date.isoformat() if self.date else None,
            "total_active_subscriptions": self.total_active_subscriptions,
            "new_subscriptions": self.new_subscriptions,
            "canceled_subscriptions": self.canceled_subscriptions,
            "paused_subscriptions": self.paused_subscriptions,
            "resumed_subscriptions": self.resumed_subscriptions,
            "total_revenue": self.total_revenue,
            "average_subscription_value": self.average_subscription_value,
            "monthly_recurring_revenue": self.monthly_recurring_revenue,
            "churn_rate": self.churn_rate,
            "conversion_rate": self.conversion_rate,
            "retention_rate": self.retention_rate,
            "currency": self.currency,
            "plan_breakdown": self.plan_breakdown,
            "delivery_breakdown": self.delivery_breakdown,
            "geographic_breakdown": self.geographic_breakdown,
            "additional_metrics": self.additional_metrics,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
