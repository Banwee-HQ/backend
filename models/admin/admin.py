"""
Consolidated admin and pricing models
Includes: PricingConfig, SubscriptionCostHistory, SubscriptionAnalytics, PaymentAnalytics
"""
from sqlalchemy import String, Float, DateTime, func, JSON, Text, Integer, Date, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from core.db import Base, GUID
from core.utils.uuid_utils import uuid7
from decimal import Decimal
from typing import Dict, Any, Optional
from datetime import datetime
import uuid


class PricingConfig(Base):
    """Admin-configurable pricing settings for subscriptions"""
    __tablename__ = "pricing_configs"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_pricing_configs_version', 'version'),
        Index('idx_pricing_configs_active', 'is_active'),
        Index('idx_pricing_configs_updated_by', 'updated_by'),
        Index('idx_pricing_configs_created_at', 'created_at'),
        {'schema': 'admin'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    # Subscription percentage (0.1% to 50%)
    subscription_percentage: Mapped[float] = mapped_column(Float, default=10.0)

    # Delivery costs by type (JSON: {"standard": 10.0, "express": 25.0, "overnight": 50.0})
    delivery_costs: Mapped[dict] = mapped_column(JSON, default=dict)

    # Tax rates by location (JSON: {"US": 0.08, "CA": 0.13, "UK": 0.20})
    tax_rates: Mapped[dict] = mapped_column(JSON, default=dict)

    # Currency settings (JSON: {"default": "USD", "supported": ["USD", "EUR", "GBP"]})
    currency_settings: Mapped[dict] = mapped_column(JSON, default={"default": "USD"})

    # Admin user who made the change
    updated_by: Mapped[uuid.UUID] = mapped_column(GUID())

    # Version for tracking configuration changes
    config_version: Mapped[str] = mapped_column(String(50), default="1.0")

    # Whether this configuration is active
    is_active: Mapped[str] = mapped_column(String(20), default="active")

    # Audit information
    change_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert pricing config to dictionary"""
        return {
            "id": str(self.id),
            "subscription_percentage": self.subscription_percentage,
            "delivery_costs": self.delivery_costs,
            "tax_rates": self.tax_rates,
            "currency_settings": self.currency_settings,
            "updated_by": str(self.updated_by),
            "version": self.version,
            "is_active": self.is_active,
            "change_reason": self.change_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


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
        {'schema': 'admin'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

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
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    # Date for this analytics record
    date: Mapped[Date] = mapped_column(Date)

    # Subscription metrics
    total_active_subscriptions: Mapped[int] = mapped_column(Integer, default=0)
    new_subscriptions: Mapped[int] = mapped_column(Integer, default=0)
    canceled_subscriptions: Mapped[int] = mapped_column(Integer, default=0)
    paused_subscriptions: Mapped[int] = mapped_column(Integer, default=0)
    resumed_subscriptions: Mapped[int] = mapped_column(Integer, default=0)

    # Revenue metrics
    total_revenue: Mapped[float] = mapped_column(Float, default=0.0)
    average_subscription_value: Mapped[float] = mapped_column(Float, default=0.0)
    monthly_recurring_revenue: Mapped[float] = mapped_column(Float, default=0.0)

    # Performance metrics
    churn_rate: Mapped[float] = mapped_column(Float, default=0.0)
    conversion_rate: Mapped[float] = mapped_column(Float, default=0.0)
    retention_rate: Mapped[float] = mapped_column(Float, default=0.0)

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
        {'schema': 'admin'},
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


class PaymentAnalytics(Base):
    """Daily payment analytics and metrics"""
    __tablename__ = "payment_analytics"

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    # Date for this analytics record
    date: Mapped[Date] = mapped_column(Date)

    # Payment volume metrics
    total_payments: Mapped[int] = mapped_column(Integer, default=0)
    successful_payments: Mapped[int] = mapped_column(Integer, default=0)
    failed_payments: Mapped[int] = mapped_column(Integer, default=0)
    pending_payments: Mapped[int] = mapped_column(Integer, default=0)

    # Success rate
    success_rate: Mapped[float] = mapped_column(Float, default=0.0)

    # Volume metrics
    total_volume: Mapped[float] = mapped_column(Float, default=0.0)
    successful_volume: Mapped[float] = mapped_column(Float, default=0.0)
    average_payment_amount: Mapped[float] = mapped_column(Float, default=0.0)

    # Currency
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Breakdown by payment method (JSON: {"card": {...}, "bank_account": {...}})
    breakdown_by_method: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Breakdown by country (JSON: {"US": {...}, "CA": {...}})
    breakdown_by_country: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Breakdown by currency (JSON: {"USD": {...}, "EUR": {...}})
    breakdown_by_currency: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Failure analysis (JSON: {"insufficient_funds": 5, "card_declined": 3})
    failure_breakdown: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Processing times (JSON: {"average_ms": 1500, "p95_ms": 3000})
    processing_metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Additional metrics (JSON)
    additional_metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        {'schema': 'admin'},
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert payment analytics to dictionary"""
        return {
            "id": str(self.id),
            "date": self.date.isoformat() if self.date else None,
            "total_payments": self.total_payments,
            "successful_payments": self.successful_payments,
            "failed_payments": self.failed_payments,
            "pending_payments": self.pending_payments,
            "success_rate": self.success_rate,
            "total_volume": self.total_volume,
            "successful_volume": self.successful_volume,
            "average_payment_amount": self.average_payment_amount,
            "currency": self.currency,
            "breakdown_by_method": self.breakdown_by_method,
            "breakdown_by_country": self.breakdown_by_country,
            "breakdown_by_currency": self.breakdown_by_currency,
            "failure_breakdown": self.failure_breakdown,
            "processing_metrics": self.processing_metrics,
            "additional_metrics": self.additional_metrics,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }