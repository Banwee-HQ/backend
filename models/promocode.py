from sqlalchemy import Column, String, Boolean, DateTime, Float, Text, Integer, Index
from core.db import BaseModel


class Promocode(BaseModel):
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
        {'extend_existing': True}
    )

    code = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    discount_type = Column(String(20), nullable=False)  # percentage, fixed
    value = Column(Float, nullable=False)  # 10 for 10% or $10
    minimum_order_amount = Column(Float, nullable=True)
    maximum_discount_amount = Column(Float, nullable=True)
    usage_limit = Column(Integer, nullable=True)
    used_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
