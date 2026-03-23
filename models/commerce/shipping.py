from sqlalchemy import Column, String, Boolean, Float, Text, Integer, Index
from core.db import BaseModel, CHAR_LENGTH


class ShippingMethod(BaseModel):
    __tablename__ = "shipping_methods"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_shipping_methods_name', 'name'),
        Index('idx_shipping_methods_active', 'is_active'),
        Index('idx_shipping_methods_price', 'price'),
        Index('idx_shipping_methods_estimated_days', 'estimated_days'),
        # Composite indexes for common queries
        Index('idx_shipping_methods_active_price', 'is_active', 'price'),
        {'extend_existing': True}
    )

    name = Column(String(CHAR_LENGTH), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    estimated_days = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)
    
    # Simple metadata
    carrier = Column(String(100), nullable=True, comment="Shipping carrier name (e.g., FedEx, UPS, DHL)")
    tracking_url_template = Column(String(500), nullable=True, comment="URL template for tracking with {tracking_number} placeholder")
