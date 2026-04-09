from sqlalchemy import String, Boolean, ForeignKey, Integer, DateTime, func, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from core.db import Base, GUID
from core.utils.uuid_utils import uuid7
from datetime import datetime as dt
from typing import Optional
import uuid as uuid_module


class Wishlist(Base):
    __tablename__ = "wishlists"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_wishlists_user_id', 'user_id'),
        Index('idx_wishlists_default', 'is_default'),
        Index('idx_wishlists_public', 'is_public'),
        Index('idx_wishlists_name', 'name'),
        # Composite indexes for common queries
        Index('idx_wishlists_user_default', 'user_id', 'is_default'),
        {'schema': 'catalog'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid_module.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[dt] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    created_by: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), nullable=True)
    updated_by: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    user_id: Mapped[uuid_module.UUID] = mapped_column(GUID(), ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(225))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    user = relationship("User", back_populates="wishlists")
    items = relationship("WishlistItem", back_populates="wishlist",
                         cascade="all, delete-orphan", lazy="selectin")


class WishlistItem(Base):
    __tablename__ = "wishlist_items"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_wishlist_items_wishlist_id', 'wishlist_id'),
        Index('idx_wishlist_items_product_id', 'product_id'),
        Index('idx_wishlist_items_variant_id', 'variant_id'),
        Index('idx_wishlist_items_created_at', 'created_at'),
        # Composite indexes for common queries
        Index('idx_wishlist_items_wishlist_product', 'wishlist_id', 'product_id'),
        {'schema': 'catalog'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid_module.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[dt] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    created_by: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), nullable=True)
    updated_by: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    wishlist_id: Mapped[uuid_module.UUID] = mapped_column(GUID(), ForeignKey("wishlists.id"))
    product_id: Mapped[uuid_module.UUID] = mapped_column(GUID(), ForeignKey("products.id"))
    variant_id: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), ForeignKey("product_variants.id"), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    # Relationships
    wishlist = relationship("Wishlist", back_populates="items")
    product = relationship("Product", back_populates="wishlist_items")
    variant = relationship("ProductVariant", foreign_keys=[variant_id])

    @property
    def added_at(self):
        """Use created_at as added_at for compatibility"""
        return self.created_at
