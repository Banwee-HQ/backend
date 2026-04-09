from sqlalchemy import String, Boolean, DateTime, func, Float, Text, Integer, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from core.db import Base, GUID
from core.utils.uuid_utils import uuid7
from datetime import datetime as dt
from typing import Optional
import uuid


class Promocode(Base):
    __tablename__ = "promocodes"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_promocodes_code', 'code'),
        Index('idx_promocodes_active', 'is_active'),
        Index('idx_promocodes_discount_type', 'discount_type'),
        Index('idx_promocodes_valid_from', 'valid_from'),
        Index('idx_promocodes_valid_until', 'valid_until'),
        Index('idx_promocodes_usage_limit', 'usage_limit'),
        Index('idx_promocodes_used_count', 'used_count'),
        # Composite indexes for common queries
        Index('idx_promocodes_active_valid', 'is_active', 'valid_from', 'valid_until'),
        {'schema': 'commerce'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    code: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    discount_type: Mapped[str] = mapped_column(String(20))  # percentage, fixed
    value: Mapped[float] = mapped_column(Float)  # 10 for 10% or $10
    minimum_order_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    maximum_discount_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    usage_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
