"""
Analytics models for tracking business metrics
Includes: UserSession, ConversionEvent, CartEvent, PurchaseMetrics
"""
from sqlalchemy import String, ForeignKey, Float, Text, Integer, DateTime, func, Boolean, Enum as SQLEnum, Index
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column
from core.db import Base, GUID
from core.utils.uuid_utils import uuid7
from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import uuid


class EventType(Enum):
    """Analytics event types"""
    PAGE_VIEW = "page_view"
    CART_ADD = "cart_add"
    CART_REMOVE = "cart_remove"
    CART_VIEW = "cart_view"
    CHECKOUT_START = "checkout_start"
    CHECKOUT_STEP = "checkout_step"
    CHECKOUT_COMPLETE = "checkout_complete"
    CHECKOUT_ABANDON = "checkout_abandon"
    PURCHASE = "purchase"
    REFUND_REQUEST = "refund_request"
    REFUND_COMPLETE = "refund_complete"
    USER_REGISTER = "user_register"
    USER_LOGIN = "user_login"


class TrafficSource(Enum):
    """Traffic source types"""
    DIRECT = "direct"
    ORGANIC_SEARCH = "organic_search"
    PAID_SEARCH = "paid_search"
    SOCIAL = "social"
    EMAIL = "email"
    REFERRAL = "referral"
    AFFILIATE = "affiliate"
    UNKNOWN = "unknown"


class UserSession(Base):
    """User session tracking for analytics"""
    __tablename__ = "user_sessions"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_user_sessions_session_id', 'session_id'),
        Index('idx_user_sessions_user_id', 'user_id'),
        Index('idx_user_sessions_created_at', 'created_at'),
        Index('idx_user_sessions_started_at', 'started_at'),
        Index('idx_user_sessions_ended_at', 'ended_at'),
        Index('idx_user_sessions_traffic_source', 'traffic_source'),
        Index('idx_user_sessions_converted', 'converted'),
        # Composite indexes for common queries
        Index('idx_user_sessions_user_created', 'user_id', 'created_at'),
        Index('idx_user_sessions_source_created', 'traffic_source', 'created_at'),
        {'schema': 'admin'},
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Session identification
    session_id: Mapped[str] = mapped_column(String(255), unique=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("accounts.users.id"), nullable=True)

    # Session metadata
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    device_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    browser: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    os: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Traffic attribution
    traffic_source: Mapped[TrafficSource] = mapped_column(SQLEnum(TrafficSource), default=TrafficSource.DIRECT)
    referrer_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    utm_source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    utm_medium: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    utm_campaign: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    utm_content: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    utm_term: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Session timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Session metrics
    page_views: Mapped[int] = mapped_column(Integer, default=0)
    events_count: Mapped[int] = mapped_column(Integer, default=0)
    converted: Mapped[bool] = mapped_column(Boolean, default=False)
    conversion_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Geographic data
    country: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="sessions")
    events = relationship("AnalyticsEvent", back_populates="session", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "session_id": self.session_id,
            "user_id": str(self.user_id) if self.user_id else None,
            "device_type": self.device_type,
            "browser": self.browser,
            "os": self.os,
            "traffic_source": self.traffic_source.value if self.traffic_source else None,
            "referrer_url": self.referrer_url,
            "utm_source": self.utm_source,
            "utm_medium": self.utm_medium,
            "utm_campaign": self.utm_campaign,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "page_views": self.page_views,
            "events_count": self.events_count,
            "converted": self.converted,
            "conversion_value": self.conversion_value,
            "country": self.country,
            "region": self.region,
            "city": self.city,
        }


class AnalyticsEvent(Base):
    """Individual analytics events"""
    __tablename__ = "analytics_events"
    __table_args__ = (
        Index('idx_analytics_events_session_id', 'session_id'),
        Index('idx_analytics_events_user_id', 'user_id'),
        Index('idx_analytics_events_type', 'event_type'),
        Index('idx_analytics_events_created_at', 'created_at'),
        Index('idx_analytics_events_order_id', 'order_id'),
        # Composite indexes for analytics queries
        Index('idx_analytics_events_type_created', 'event_type', 'created_at'),
        Index('idx_analytics_events_user_type', 'user_id', 'event_type'),
        Index('idx_analytics_events_session_type', 'session_id', 'event_type'),
        {'schema': 'admin'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Event identification
    session_id: Mapped[str] = mapped_column(String(255), ForeignKey("admin.user_sessions.session_id"))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("accounts.users.id"), nullable=True)
    event_type: Mapped[EventType] = mapped_column(SQLEnum(EventType))

    # Event data
    page_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    page_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    event_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # E-commerce specific fields
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("commerce.orders.id"), nullable=True)
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    variant_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Financial data
    revenue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timing
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    session = relationship("UserSession", back_populates="events")
    user = relationship("User")
    order = relationship("Order")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "session_id": self.session_id,
            "user_id": str(self.user_id) if self.user_id else None,
            "event_type": self.event_type.value if self.event_type else None,
            "page_url": self.page_url,
            "page_title": self.page_title,
            "event_data": self.event_data,
            "order_id": str(self.order_id) if self.order_id else None,
            "product_id": str(self.product_id) if self.product_id else None,
            "variant_id": str(self.variant_id) if self.variant_id else None,
            "category": self.category,
            "revenue": self.revenue,
            "quantity": self.quantity,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class ConversionFunnel(Base):
    """Conversion funnel tracking"""
    __tablename__ = "conversion_funnels"
    __table_args__ = (
        Index('idx_conversion_funnels_session_id', 'session_id'),
        Index('idx_conversion_funnels_user_id', 'user_id'),
        Index('idx_conversion_funnels_created_at', 'created_at'),
        Index('idx_conversion_funnels_step', 'current_step'),
        {'schema': 'admin'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Funnel identification
    session_id: Mapped[str] = mapped_column(String(255), ForeignKey("admin.user_sessions.session_id"))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("accounts.users.id"), nullable=True)

    # Funnel steps (0-based)
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    max_step_reached: Mapped[int] = mapped_column(Integer, default=0)

    # Step timestamps
    landing_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_view_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cart_add_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    checkout_start_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    purchase_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Funnel metadata
    abandoned_at_step: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    abandoned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Financial data
    cart_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    purchase_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Relationships
    session = relationship("UserSession")
    user = relationship("User")


class CustomerLifecycleMetrics(Base):
    """Customer lifecycle and repeat purchase tracking"""
    __tablename__ = "customer_lifecycle_metrics"
    __table_args__ = (
        Index('idx_customer_lifecycle_user_id', 'user_id'),
        Index('idx_customer_lifecycle_created_at', 'created_at'),
        Index('idx_customer_lifecycle_segment', 'customer_segment'),
        {'schema': 'admin'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Customer identification
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("accounts.users.id"), unique=True)

    # Registration and first purchase
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_purchase_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    time_to_first_purchase_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Purchase behavior
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    total_revenue: Mapped[float] = mapped_column(Float, default=0.0)
    average_order_value: Mapped[float] = mapped_column(Float, default=0.0)

    # Timing metrics
    last_purchase_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    days_since_last_purchase: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    average_days_between_orders: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Refund metrics
    total_refunds: Mapped[int] = mapped_column(Integer, default=0)
    total_refund_amount: Mapped[float] = mapped_column(Float, default=0.0)
    refund_rate: Mapped[float] = mapped_column(Float, default=0.0)

    # Customer segmentation
    customer_segment: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    lifetime_value: Mapped[float] = mapped_column(Float, default=0.0)
    predicted_ltv: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Engagement metrics
    total_sessions: Mapped[int] = mapped_column(Integer, default=0)
    total_page_views: Mapped[int] = mapped_column(Integer, default=0)
    average_session_duration: Mapped[float] = mapped_column(Float, default=0.0)

    # Last updated
    metrics_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="lifecycle_metrics")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": str(self.user_id),
            "registered_at": self.registered_at.isoformat() if self.registered_at else None,
            "first_purchase_at": self.first_purchase_at.isoformat() if self.first_purchase_at else None,
            "time_to_first_purchase_hours": self.time_to_first_purchase_hours,
            "total_orders": self.total_orders,
            "total_revenue": self.total_revenue,
            "average_order_value": self.average_order_value,
            "last_purchase_at": self.last_purchase_at.isoformat() if self.last_purchase_at else None,
            "days_since_last_purchase": self.days_since_last_purchase,
            "average_days_between_orders": self.average_days_between_orders,
            "total_refunds": self.total_refunds,
            "total_refund_amount": self.total_refund_amount,
            "refund_rate": self.refund_rate,
            "customer_segment": self.customer_segment,
            "lifetime_value": self.lifetime_value,
            "predicted_ltv": self.predicted_ltv,
            "total_sessions": self.total_sessions,
            "total_page_views": self.total_page_views,
            "average_session_duration": self.average_session_duration,
            "metrics_updated_at": self.metrics_updated_at.isoformat() if self.metrics_updated_at else None,
        }