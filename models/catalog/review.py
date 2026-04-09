from sqlalchemy import Column, Boolean, ForeignKey, Text, Integer, DateTime, func, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from core.db import Base, GUID
from core.utils.uuid_utils import uuid7


class Review(Base):
    __tablename__ = "reviews"

    # Common fields (previously from BaseModel)
    id = Column(GUID(), primary_key=True, default=uuid7, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    created_by = Column(GUID(), nullable=True, index=True)
    updated_by = Column(GUID(), nullable=True)
    version = Column(Integer, default=1, nullable=False)

    product_id = Column(GUID(), ForeignKey("products.id"), nullable=False)
    user_id = Column(GUID(), ForeignKey(
        "users.id"), nullable=False)
    rating = Column(Integer, nullable=False)  # 1-5 stars
    comment = Column(Text, nullable=True)
    is_verified_purchase = Column(Boolean, default=False)
    is_approved = Column(Boolean, default=True)

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
        {'extend_existing': True}
    )

    # Relationships
    product = relationship("Product", back_populates="reviews")
    user = relationship("User", back_populates="reviews")
