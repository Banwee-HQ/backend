"""
Consolidated subscription models
Includes: Subscription and related subscription models
Optimized for PostgreSQL with partial indexes for active subscriptions and products
"""
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Float, Table, JSON, Text, Integer, func, Index, Column
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from core.db import Base, GUID
from core.utils.uuid_utils import uuid7
from typing import Dict, Any, Optional
from datetime import datetime as dt
import uuid as uuid_module

# --- Association table: Subscription <-> ProductVariant ---
subscription_product_association = Table(
    "subscription_product_association",
    Base.metadata,
    Column("subscription_id", GUID(), ForeignKey("subscriptions.id"), primary_key=True),
    Column("product_variant_id", GUID(), ForeignKey("product_variants.id"), primary_key=True),
    Index('idx_sub_product_association_variant', 'product_variant_id'),
    extend_existing=True
)


class SubscriptionProduct(Base):
    """Tracks individual products within subscriptions with removal tracking"""
    __tablename__ = "subscription_products"

    # Common fields (previously from BaseModel)
    id: Mapped[uuid_module.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[dt] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    created_by: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), nullable=True)
    updated_by: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    subscription_id: Mapped[uuid_module.UUID] = mapped_column(GUID(), ForeignKey("subscriptions.id", ondelete="CASCADE"))
    product_id: Mapped[uuid_module.UUID] = mapped_column(GUID(), ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Float)
    total_price: Mapped[float] = mapped_column(Float)
    added_at: Mapped[dt] = mapped_column(DateTime(timezone=True), server_default="NOW()")

    # Removal tracking
    removed_at: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_by: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True)

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
        {'extend_existing': True}
    )

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

    # Common fields (previously from BaseModel)
    id: Mapped[uuid_module.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[dt] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    created_by: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), nullable=True)
    updated_by: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    # --- Core fields ---
    user_id: Mapped[uuid_module.UUID] = mapped_column(GUID(), ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="active")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    billing_cycle: Mapped[str] = mapped_column(String(20), default="monthly")
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True)
    current_period_start: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_billing_date: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), nullable=True)
    pause_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_payment_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payment_retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_payment_attempt: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_date: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Payment info ---
    payment_gateway: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # --- Delivery info ---
    delivery_type: Mapped[Optional[str]] = mapped_column(String(50), default="standard")
    delivery_address_id: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), ForeignKey("addresses.id"), nullable=True)

    # --- Pricing at creation ---
    price_at_creation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    variant_prices_at_creation: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    shipping_amount_at_creation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tax_amount_at_creation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tax_rate_at_creation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # --- Current/dynamic pricing ---
    current_variant_prices: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    current_shipping_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_tax_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_tax_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # --- Products & variants ---
    variant_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    subscription_products = relationship("SubscriptionProduct", back_populates="subscription", lazy="select")
    products = relationship(
        "ProductVariant",
        secondary=subscription_product_association,
        backref="subscriptions_containing",
        lazy="selectin"
    )

    # --- Metadata ---
    subscription_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # --- Discount fields ---
    discount_id = Column(GUID(), ForeignKey("promocodes.id"), nullable=True)
    discount_type = Column(String(20), nullable=True)  # "percentage" or "fixed"
    discount_value = Column(Float, nullable=True)
    discount_code = Column(String(50), nullable=True)

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
        {'extend_existing': True}
    )

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
