"""
Pricing configuration models for subscriptions and commerce
Includes: PricingConfig for admin-configurable pricing settings
"""
from sqlalchemy import String, Float, DateTime, func, JSON, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from core.db import Base, GUID
from core.utils.uuid_utils import uuid7
from typing import Dict, Any, Optional
from datetime import datetime
import uuid


class PricingConfig(Base):
    """Admin-configurable pricing settings for subscriptions"""
    __tablename__ = "pricing_configs"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_pricing_configs_version', 'config_version'),
        Index('idx_pricing_configs_active', 'is_active'),
        Index('idx_pricing_configs_updated_by', 'updated_by'),
        Index('idx_pricing_configs_created_at', 'created_at'),
        {'schema': 'commerce'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

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
            "config_version": self.config_version,
            "is_active": self.is_active,
            "change_reason": self.change_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
