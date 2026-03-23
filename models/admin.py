"""
Consolidated admin and pricing models
Includes: PricingConfig, SubscriptionCostHistory, SubscriptionAnalytics, PaymentAnalytics
"""
from sqlalchemy import Column, String, Float, DateTime, JSON, Text, Integer, Date, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from core.db import BaseModel, GUID
from decimal import Decimal
from typing import Dict, Any


class PricingConfig(BaseModel):
    """Admin-configurable pricing settings for subscriptions"""
    __tablename__ = "pricing_configs"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_pricing_configs_version', 'version'),
        Index('idx_pricing_configs_active', 'is_active'),
        Index('idx_pricing_configs_updated_by', 'updated_by'),
        Index('idx_pricing_configs_created_at', 'created_at'),
        {'extend_existing': True}
    )

    # Subscription percentage (0.1% to 50%)
    subscription_percentage = Column(Float, nullable=False, default=10.0)
    
    # Delivery costs by type (JSON: {"standard": 10.0, "express": 25.0, "overnight": 50.0})
    delivery_costs = Column(JSON, nullable=False, default={})
    
    # Tax rates by location (JSON: {"US": 0.08, "CA": 0.13, "UK": 0.20})
    tax_rates = Column(JSON, nullable=False, default={})
    
    # Currency settings (JSON: {"default": "USD", "supported": ["USD", "EUR", "GBP"]})
    currency_settings = Column(JSON, nullable=False, default={"default": "USD"})
    
    # Admin user who made the change
    updated_by = Column(GUID(), nullable=False)
    
    # Version for tracking configuration changes
    version = Column(String(50), nullable=False, default="1.0")
    
    # Whether this configuration is active
    is_active = Column(String(20), nullable=False, default="active")
    
    # Audit information
    change_reason = Column(Text, nullable=True)
    
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


class SubscriptionCostHistory(BaseModel):
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
        {'extend_existing': True}
    )

    subscription_id = Column(GUID(), nullable=False, index=True)
    
    # Old cost breakdown (JSON)
    old_cost_breakdown = Column(JSON, nullable=True)
    
    # New cost breakdown (JSON)
    new_cost_breakdown = Column(JSON, nullable=False)
    
    # Reason for cost change
    change_reason = Column(String(100), nullable=False)  # "admin_percentage_change", "variant_price_change", etc.
    
    # When the change becomes effective
    effective_date = Column(DateTime(timezone=True), nullable=False)
    
    # Admin user who triggered the change (if applicable)
    changed_by = Column(GUID(), nullable=True)
    
    # Additional metadata
    pricing_metadata = Column(JSON, nullable=True)
    
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


class SubscriptionAnalytics(BaseModel):
    """Daily subscription analytics and metrics"""
    __tablename__ = "subscription_analytics"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_subscription_analytics_date', 'date'),
        Index('idx_subscription_analytics_currency', 'currency'),
        Index('idx_subscription_analytics_revenue', 'total_revenue'),
        Index('idx_subscription_analytics_mrr', 'monthly_recurring_revenue'),
        Index('idx_subscription_analytics_churn_rate', 'churn_rate'),
        {'extend_existing': True}
    )

    # Date for this analytics record
    date = Column(Date, nullable=False, index=True)
    
    # Subscription metrics
    total_active_subscriptions = Column(Integer, nullable=False, default=0)
    new_subscriptions = Column(Integer, nullable=False, default=0)
    canceled_subscriptions = Column(Integer, nullable=False, default=0)
    paused_subscriptions = Column(Integer, nullable=False, default=0)
    resumed_subscriptions = Column(Integer, nullable=False, default=0)
    
    # Revenue metrics
    total_revenue = Column(Float, nullable=False, default=0.0)
    average_subscription_value = Column(Float, nullable=False, default=0.0)
    monthly_recurring_revenue = Column(Float, nullable=False, default=0.0)
    
    # Performance metrics
    churn_rate = Column(Float, nullable=False, default=0.0)
    conversion_rate = Column(Float, nullable=False, default=0.0)
    retention_rate = Column(Float, nullable=False, default=0.0)
    
    # Currency
    currency = Column(String(3), nullable=False, default="USD")
    
    # Breakdown by subscription type/plan (JSON)
    plan_breakdown = Column(JSON, nullable=True)
    
    # Breakdown by delivery type (JSON)
    delivery_breakdown = Column(JSON, nullable=True)
    
    # Geographic breakdown (JSON)
    geographic_breakdown = Column(JSON, nullable=True)
    
    # Additional metrics (JSON)
    additional_metrics = Column(JSON, nullable=True)
    
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


class PaymentAnalytics(BaseModel):
    """Daily payment analytics and metrics"""
    __tablename__ = "payment_analytics"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_payment_analytics_date', 'date'),
        Index('idx_payment_analytics_currency', 'currency'),
        Index('idx_payment_analytics_success_rate', 'success_rate'),
        Index('idx_payment_analytics_total_volume', 'total_volume'),
        Index('idx_payment_analytics_total_payments', 'total_payments'),
        {'extend_existing': True}
    )

    # Date for this analytics record
    date = Column(Date, nullable=False, index=True)
    
    # Payment volume metrics
    total_payments = Column(Integer, nullable=False, default=0)
    successful_payments = Column(Integer, nullable=False, default=0)
    failed_payments = Column(Integer, nullable=False, default=0)
    pending_payments = Column(Integer, nullable=False, default=0)
    
    # Success rate
    success_rate = Column(Float, nullable=False, default=0.0)
    
    # Volume metrics
    total_volume = Column(Float, nullable=False, default=0.0)
    successful_volume = Column(Float, nullable=False, default=0.0)
    average_payment_amount = Column(Float, nullable=False, default=0.0)
    
    # Currency
    currency = Column(String(3), nullable=False, default="USD")
    
    # Breakdown by payment method (JSON: {"card": {...}, "bank_account": {...}})
    breakdown_by_method = Column(JSON, nullable=True)
    
    # Breakdown by country (JSON: {"US": {...}, "CA": {...}})
    breakdown_by_country = Column(JSON, nullable=True)
    
    # Breakdown by currency (JSON: {"USD": {...}, "EUR": {...}})
    breakdown_by_currency = Column(JSON, nullable=True)
    
    # Failure analysis (JSON: {"insufficient_funds": 5, "card_declined": 3})
    failure_breakdown = Column(JSON, nullable=True)
    
    # Processing times (JSON: {"average_ms": 1500, "p95_ms": 3000})
    processing_metrics = Column(JSON, nullable=True)
    
    # Additional metrics (JSON)
    additional_metrics = Column(JSON, nullable=True)
    
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