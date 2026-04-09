"""
Validation rules models for tax and shipping fallback calculations
"""
from sqlalchemy import String, Boolean, DateTime, func, Float, Text, Integer, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from core.db import Base, GUID
from core.utils.uuid_utils import uuid7
from typing import Dict, Any, Optional
from datetime import datetime
import uuid


class TaxValidationRule(Base):
    """Tax validation rules for fallback rate application"""
    __tablename__ = "tax_rules"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_tax_rules_location_code', 'location_code'),
        Index('idx_tax_rules_active', 'is_active'),
        Index('idx_tax_rules_tax_rate', 'tax_rate'),
        # Composite indexes for common queries
        Index('idx_tax_rules_location_active', 'location_code', 'is_active'),
        {'schema': 'system'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    location_code: Mapped[str] = mapped_column(String(10))  # Country/state code (e.g., "US-CA", "GB")
    tax_rate: Mapped[float] = mapped_column(Float)  # Tax rate as decimal (e.g., 0.08 for 8%)
    minimum_tax: Mapped[float] = mapped_column(Float, default=0.01)  # Minimum tax amount
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert tax rule to dictionary for API responses"""
        return {
            "id": str(self.id),
            "location_code": self.location_code,
            "tax_rate": self.tax_rate,
            "minimum_tax": self.minimum_tax,
            "is_active": self.is_active,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def calculate_tax(self, amount: float) -> float:
        """Calculate tax amount with minimum enforcement"""
        if not self.is_active:
            return 0.0
        
        calculated_tax = amount * self.tax_rate
        return max(calculated_tax, self.minimum_tax)


class ShippingValidationRule(Base):
    """Shipping validation rules for fallback rate application"""
    __tablename__ = "shipping_rules"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_shipping_rules_location_code', 'location_code'),
        Index('idx_shipping_rules_active', 'is_active'),
        Index('idx_shipping_rules_weight_range', 'weight_min', 'weight_max'),
        Index('idx_shipping_rules_base_rate', 'base_rate'),
        # Composite indexes for common queries
        Index('idx_shipping_rules_location_active', 'location_code', 'is_active'),
        Index('idx_shipping_rules_weight_active', 'weight_min', 'weight_max', 'is_active'),
        {'schema': 'system'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    location_code: Mapped[str] = mapped_column(String(10))  # Country/state code (e.g., "US-CA", "GB")
    weight_min: Mapped[float] = mapped_column(Float, default=0.0)  # Minimum weight in kg
    weight_max: Mapped[float] = mapped_column(Float)  # Maximum weight in kg
    base_rate: Mapped[float] = mapped_column(Float)  # Base shipping rate
    minimum_shipping: Mapped[float] = mapped_column(Float, default=0.01)  # Minimum shipping amount
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert shipping rule to dictionary for API responses"""
        return {
            "id": str(self.id),
            "location_code": self.location_code,
            "weight_min": self.weight_min,
            "weight_max": self.weight_max,
            "base_rate": self.base_rate,
            "minimum_shipping": self.minimum_shipping,
            "is_active": self.is_active,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def calculate_shipping(self, weight: float) -> float:
        """Calculate shipping amount with minimum enforcement"""
        if not self.is_active:
            return 0.0
        
        if not (self.weight_min <= weight <= self.weight_max):
            return 0.0
        
        # Simple calculation: base rate + weight-based adjustment
        calculated_shipping = self.base_rate + (weight * 0.5)  # $0.50 per kg
        return max(calculated_shipping, self.minimum_shipping)

    def applies_to_weight(self, weight: float) -> bool:
        """Check if this rule applies to the given weight"""
        return self.is_active and self.weight_min <= weight <= self.weight_max