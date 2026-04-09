from sqlalchemy import Boolean, ForeignKey, Text, Integer, DateTime, func, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from core.db import Base, GUID
from core.utils.uuid_utils import uuid7
from datetime import datetime as dt
from typing import Optional
import uuid as uuid_module


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_reviews_product_id', 'product_id'),
        Index('idx_reviews_user_id', 'user_id'),
        Index('idx_reviews_rating', 'rating'),
        Index('idx_reviews_verified', 'is_verified_purchase'),
        Index('idx_reviews_approved', 'is_approved'),
        Index('idx_reviews_created_at', 'created_at'),
        # Composite indexes for common queries
        Index('idx_reviews_product_approved', 'product_id', 'is_approved'),
        Index('idx_reviews_product_rating', 'product_id', 'rating'),
        Index('idx_reviews_user_approved', 'user_id', 'is_approved'),
        {'schema': 'catalog'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid_module.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[dt] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    created_by: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), nullable=True)
    updated_by: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    product_id: Mapped[uuid_module.UUID] = mapped_column(GUID(), ForeignKey("products.id"))
    user_id: Mapped[uuid_module.UUID] = mapped_column(GUID(), ForeignKey("users.id"))
    rating: Mapped[int] = mapped_column(Integer)  # 1-5 stars
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_verified_purchase: Mapped[bool] = mapped_column(Boolean, default=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    product = relationship("Product", back_populates="reviews")
    user = relationship("User", back_populates="reviews")
