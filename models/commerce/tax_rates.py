from sqlalchemy import String, Float, Boolean, DateTime, func, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, datetime as dt
from typing import Optional
import uuid as uuid_module
from core.db import Base, GUID
from core.utils.uuid_utils import uuid7


class TaxRate(Base):
    """Tax rates by country and province/state"""
    __tablename__ = "tax_rates"

    # Common fields (previously from BaseModel)
    id: Mapped[uuid_module.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[dt] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    created_by: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), nullable=True)
    updated_by: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    country_code: Mapped[str] = mapped_column(String(2))  # ISO 3166-1 alpha-2
    country_name: Mapped[str] = mapped_column(String(100))
    province_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # State/Province code
    province_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tax_rate: Mapped[float] = mapped_column(Float)  # Tax rate as decimal (e.g., 0.13 for 13%)
    tax_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # e.g., "GST", "VAT", "Sales Tax"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    effective_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Composite index for fast lookups
    __table_args__ = (
        Index('idx_tax_country_province', 'country_code', 'province_code'),
    )

    def __repr__(self):
        location = f"{self.country_code}"
        if self.province_code:
            location += f"-{self.province_code}"
        return f"<TaxRate {location}: {self.tax_rate * 100}%>"
