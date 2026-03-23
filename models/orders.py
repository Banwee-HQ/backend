"""
Optimized order models with hard delete only
Includes: Order, OrderItem, TrackingEvent
"""
from sqlalchemy import Column, String, ForeignKey, Float, Text, Integer, DateTime, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from core.db import BaseModel, CHAR_LENGTH, GUID, Index
from enum import Enum


class OrderStatus(str, Enum):
    """Order status types"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentStatus(str, Enum):
    """Payment status types"""
    PENDING = "pending"
    AUTHORIZED = "authorized"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class FulfillmentStatus(str, Enum):
    """Fulfillment status types"""
    UNFULFILLED = "unfulfilled"
    PARTIAL = "partial"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class OrderSource(str, Enum):
    """Order source types"""
    WEB = "web"
    MOBILE = "mobile"
    API = "api"
    ADMIN = "admin"


class Order(BaseModel):
    """Simplified order model with essential pricing fields only"""
    __tablename__ = "orders"
    __table_args__ = (
        # Optimized indexes for common order queries
        Index('idx_orders_user_status', 'user_id', 'order_status'),
        Index('idx_orders_subscription_id', 'subscription_id'),
        Index('idx_orders_payment_status', 'payment_status', 'created_at'),
        Index('idx_orders_fulfillment_status', 'fulfillment_status'),
        Index('idx_orders_order_number', 'order_number'),
        Index('idx_orders_total_currency', 'total_amount', 'currency'),
        Index('idx_orders_tracking', 'tracking_number'),
        Index('idx_orders_confirmed_shipped', 'confirmed_at', 'shipped_at'),
        # GIN index for address queries
        Index('idx_orders_shipping_address', 'shipping_address', postgresql_using='gin'),
        {'extend_existing': True}
    )

    # Order identification
    order_number = Column(String(50), unique=True, nullable=False)
    
    # Customer reference
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    guest_email = Column(String(CHAR_LENGTH), nullable=True)  # For guest orders
    
    # Subscription reference for recurring orders
    subscription_id = Column(GUID(), ForeignKey("subscriptions.id"), nullable=True)
    
    # Status fields as columns for fast querying and indexing
    order_status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING, nullable=False)
    payment_status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    fulfillment_status = Column(SQLEnum(FulfillmentStatus), default=FulfillmentStatus.UNFULFILLED, nullable=False)
    
    # Simplified financial information - only the essentials
    subtotal = Column(Float, nullable=False)  # Sum of all product variant prices
    shipping_cost = Column(Float, default=0.0)  # Shipping cost (renamed from shipping_amount)
    discount_amount = Column(Float, default=0.0)  # Discount amount applied to order
    tax_amount = Column(Float, default=0.0)  # Tax amount
    tax_rate = Column(Float, default=0.0)  # Tax rate applied (e.g., 0.08 for 8%)
    total_amount = Column(Float, nullable=False)  # Final total
    currency = Column(String(3), default="USD")
    
    # Shipping information as columns for frequent access
    shipping_method = Column(String(100), nullable=True)
    tracking_number = Column(String(255), nullable=True)
    carrier = Column(String(100), nullable=True)
    
    # Use JSONB only for complex address data that benefits from querying
    billing_address = Column(JSONB, nullable=False)
    shipping_address = Column(JSONB, nullable=False)
    
    # Important lifecycle dates as columns
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    shipped_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    
    # Notes as text (simple storage)
    customer_notes = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)
    
    # Failure tracking
    failure_reason = Column(Text, nullable=True)
    
    # Idempotency and source tracking
    idempotency_key = Column(String(255), unique=True, nullable=True)
    source = Column(SQLEnum(OrderSource), default=OrderSource.WEB, nullable=False)  # web, mobile, api
    
    # Legacy fields for backward compatibility
    status = Column(String(50), default="pending")  # Keep for existing code
    shipping_address_id = Column(GUID(), nullable=True)  # Legacy FK
    shipping_method_id = Column(GUID(), nullable=True)  # Legacy FK
    payment_method_id = Column(GUID(), nullable=True)  # Legacy FK
    promocode_id = Column(GUID(), nullable=True)  # Legacy FK
    carrier_name = Column(String(100), nullable=True)  # Legacy field
    notes = Column(Text, nullable=True)  # Legacy field

    # Relationships with optimized lazy loading
    user = relationship("User", back_populates="orders")
    subscription = relationship("Subscription", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan", lazy="selectin")
    tracking_events = relationship("TrackingEvent", back_populates="order", cascade="all, delete-orphan", lazy="select")
    transactions = relationship("Transaction", back_populates="order", lazy="select")
    payment_intents = relationship("PaymentIntent", back_populates="order", lazy="select")
    refunds = relationship("Refund", back_populates="order", lazy="select")
    shipments = relationship("ShipmentTracking", back_populates="order", cascade="all, delete-orphan", lazy="select")

    def to_dict(self) -> dict:
        """Convert order to dictionary for API responses"""
        return {
            "id": str(self.id),
            "order_number": self.order_number,
            "user_id": str(self.user_id),
            "guest_email": self.guest_email,
            "order_status": self.order_status,
            "payment_status": self.payment_status,
            "fulfillment_status": self.fulfillment_status,
            "subtotal": self.subtotal,
            "shipping_cost": self.shipping_cost,
            "discount_amount": self.discount_amount,
            "tax_amount": self.tax_amount,
            "tax_rate": self.tax_rate,
            "total_amount": self.total_amount,
            "currency": self.currency,
            "shipping_method": self.shipping_method,
            "tracking_number": self.tracking_number,
            "carrier": self.carrier,
            "billing_address": self.billing_address,
            "shipping_address": self.shipping_address,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "shipped_at": self.shipped_at.isoformat() if self.shipped_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "customer_notes": self.customer_notes,
            "internal_notes": self.internal_notes,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class OrderItem(BaseModel):
    """Order items - hard delete with orders"""
    __tablename__ = "order_items"
    __table_args__ = (
        Index('idx_order_items_order_id', 'order_id'),
        Index('idx_order_items_variant_id', 'variant_id'),
        {'extend_existing': True}
    )

    order_id = Column(GUID(), ForeignKey("orders.id"), nullable=False)
    variant_id = Column(GUID(), ForeignKey("product_variants.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    price_per_unit = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)

    # Relationships
    order = relationship("Order", back_populates="items")
    variant = relationship("ProductVariant", back_populates="order_items")
    shipment = relationship("ShipmentTracking", back_populates="order_item", lazy="select")

    def to_dict(self) -> dict:
        """Convert order item to dictionary"""
        return {
            "id": str(self.id),
            "order_id": str(self.order_id),
            "variant_id": str(self.variant_id),
            "quantity": self.quantity,
            "price_per_unit": self.price_per_unit,
            "total_price": self.total_price,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TrackingEvent(BaseModel):
    """Order tracking events - hard delete with orders"""
    __tablename__ = "tracking_events"
    __table_args__ = (
        Index('idx_tracking_events_order_id', 'order_id'),
        Index('idx_tracking_events_created_at', 'created_at'),
        {'extend_existing': True}
    )

    order_id = Column(GUID(), ForeignKey("orders.id"), nullable=False)
    status = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String(255), nullable=True)

    # Relationships
    order = relationship("Order", back_populates="tracking_events")

    def to_dict(self) -> dict:
        """Convert tracking event to dictionary"""
        return {
            "id": str(self.id),
            "order_id": str(self.order_id),
            "status": self.status,
            "description": self.description,
            "location": self.location,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }