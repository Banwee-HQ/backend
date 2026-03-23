"""
Analytics models for tracking business metrics
Includes: UserSession, ConversionEvent, CartEvent, PurchaseMetrics
"""
from sqlalchemy import Column, String, ForeignKey, Float, Text, Integer, DateTime, Boolean, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from core.db import BaseModel, GUID, Index
from enum import Enum
from typing import Dict, Any
from datetime import datetime, timezone


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


class UserSession(BaseModel):
    """User session tracking for analytics"""
    __tablename__ = "user_sessions"
    __table_args__ = (
        Index('idx_user_sessions_user_id', 'user_id'),
        Index('idx_user_sessions_session_id', 'session_id'),
        Index('idx_user_sessions_created_at', 'created_at'),
        Index('idx_user_sessions_source', 'traffic_source'),
        Index('idx_user_sessions_device', 'device_type'),
        # Composite indexes for analytics queries
        Index('idx_user_sessions_user_created', 'user_id', 'created_at'),
        Index('idx_user_sessions_source_created', 'traffic_source', 'created_at'),
        {'extend_existing': True}
    )

    # Session identification
    session_id = Column(String(255), unique=True, nullable=False)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=True)  # Null for anonymous sessions
    
    # Session metadata
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible
    user_agent = Column(Text, nullable=True)
    device_type = Column(String(50), nullable=True)  # mobile, desktop, tablet
    browser = Column(String(100), nullable=True)
    os = Column(String(100), nullable=True)
    
    # Traffic attribution
    traffic_source = Column(SQLEnum(TrafficSource), default=TrafficSource.DIRECT)
    referrer_url = Column(Text, nullable=True)
    utm_source = Column(String(255), nullable=True)
    utm_medium = Column(String(255), nullable=True)
    utm_campaign = Column(String(255), nullable=True)
    utm_content = Column(String(255), nullable=True)
    utm_term = Column(String(255), nullable=True)
    
    # Session timing
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    
    # Session metrics
    page_views = Column(Integer, default=0)
    events_count = Column(Integer, default=0)
    converted = Column(Boolean, default=False)
    conversion_value = Column(Float, nullable=True)
    
    # Geographic data
    country = Column(String(2), nullable=True)  # ISO country code
    region = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    
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


class AnalyticsEvent(BaseModel):
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
        {'extend_existing': True}
    )

    # Event identification
    session_id = Column(String(255), ForeignKey("user_sessions.session_id"), nullable=False)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    event_type = Column(SQLEnum(EventType), nullable=False)
    
    # Event data
    page_url = Column(Text, nullable=True)
    page_title = Column(String(500), nullable=True)
    event_data = Column(JSONB, default=dict)  # Flexible event properties
    
    # E-commerce specific fields
    order_id = Column(GUID(), ForeignKey("orders.id"), nullable=True)
    product_id = Column(GUID(), nullable=True)
    variant_id = Column(GUID(), nullable=True)
    category = Column(String(255), nullable=True)
    
    # Financial data
    revenue = Column(Float, nullable=True)
    quantity = Column(Integer, nullable=True)
    
    # Timing
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
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


class ConversionFunnel(BaseModel):
    """Conversion funnel tracking"""
    __tablename__ = "conversion_funnels"
    __table_args__ = (
        Index('idx_conversion_funnels_session_id', 'session_id'),
        Index('idx_conversion_funnels_user_id', 'user_id'),
        Index('idx_conversion_funnels_created_at', 'created_at'),
        Index('idx_conversion_funnels_step', 'current_step'),
        {'extend_existing': True}
    )

    # Funnel identification
    session_id = Column(String(255), ForeignKey("user_sessions.session_id"), nullable=False)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    
    # Funnel steps (0-based)
    current_step = Column(Integer, default=0)  # 0=landing, 1=product_view, 2=cart_add, 3=checkout_start, 4=purchase
    max_step_reached = Column(Integer, default=0)
    
    # Step timestamps
    landing_at = Column(DateTime(timezone=True), nullable=True)
    product_view_at = Column(DateTime(timezone=True), nullable=True)
    cart_add_at = Column(DateTime(timezone=True), nullable=True)
    checkout_start_at = Column(DateTime(timezone=True), nullable=True)
    purchase_at = Column(DateTime(timezone=True), nullable=True)
    
    # Funnel metadata
    abandoned_at_step = Column(Integer, nullable=True)
    abandoned_at = Column(DateTime(timezone=True), nullable=True)
    completed = Column(Boolean, default=False)
    
    # Financial data
    cart_value = Column(Float, nullable=True)
    purchase_value = Column(Float, nullable=True)
    
    # Relationships
    session = relationship("UserSession")
    user = relationship("User")


class CustomerLifecycleMetrics(BaseModel):
    """Customer lifecycle and repeat purchase tracking"""
    __tablename__ = "customer_lifecycle_metrics"
    __table_args__ = (
        Index('idx_customer_lifecycle_user_id', 'user_id'),
        Index('idx_customer_lifecycle_created_at', 'created_at'),
        Index('idx_customer_lifecycle_segment', 'customer_segment'),
        {'extend_existing': True}
    )

    # Customer identification
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False, unique=True)
    
    # Registration and first purchase
    registered_at = Column(DateTime(timezone=True), nullable=False)
    first_purchase_at = Column(DateTime(timezone=True), nullable=True)
    time_to_first_purchase_hours = Column(Float, nullable=True)
    
    # Purchase behavior
    total_orders = Column(Integer, default=0)
    total_revenue = Column(Float, default=0.0)
    average_order_value = Column(Float, default=0.0)
    
    # Timing metrics
    last_purchase_at = Column(DateTime(timezone=True), nullable=True)
    days_since_last_purchase = Column(Integer, nullable=True)
    average_days_between_orders = Column(Float, nullable=True)
    
    # Refund metrics
    total_refunds = Column(Integer, default=0)
    total_refund_amount = Column(Float, default=0.0)
    refund_rate = Column(Float, default=0.0)  # Percentage
    
    # Customer segmentation
    customer_segment = Column(String(50), nullable=True)  # new, active, at_risk, churned, vip
    lifetime_value = Column(Float, default=0.0)
    predicted_ltv = Column(Float, nullable=True)
    
    # Engagement metrics
    total_sessions = Column(Integer, default=0)
    total_page_views = Column(Integer, default=0)
    average_session_duration = Column(Float, default=0.0)
    
    # Last updated
    metrics_updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
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