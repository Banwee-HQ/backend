from sqlalchemy import Column, String, Boolean, ForeignKey, Integer, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from core.db import BaseModel, GUID


class Wishlist(BaseModel):
    __tablename__ = "wishlists"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_wishlists_user_id', 'user_id'),
        Index('idx_wishlists_default', 'is_default'),
        Index('idx_wishlists_public', 'is_public'),
        Index('idx_wishlists_name', 'name'),
        # Composite indexes for common queries
        Index('idx_wishlists_user_default', 'user_id', 'is_default'),
        {'extend_existing': True}
    )

    user_id = Column(GUID(), ForeignKey(
        "users.id"), nullable=False)
    name = Column(String(225), nullable=False)
    is_default = Column(Boolean, default=False)
    is_public = Column(Boolean, default=False)

    # Relationships
    user = relationship("User", back_populates="wishlists")
    items = relationship("WishlistItem", back_populates="wishlist",
                         cascade="all, delete-orphan", lazy="selectin")


class WishlistItem(BaseModel):
    __tablename__ = "wishlist_items"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_wishlist_items_wishlist_id', 'wishlist_id'),
        Index('idx_wishlist_items_product_id', 'product_id'),
        Index('idx_wishlist_items_variant_id', 'variant_id'),
        Index('idx_wishlist_items_created_at', 'created_at'),
        # Composite indexes for common queries
        Index('idx_wishlist_items_wishlist_product', 'wishlist_id', 'product_id'),
        {'extend_existing': True}
    )

    wishlist_id = Column(GUID(), ForeignKey(
        "wishlists.id"), nullable=False)
    product_id = Column(GUID(), ForeignKey(
        "products.id"), nullable=False)
    variant_id = Column(GUID(), ForeignKey(
        "product_variants.id"), nullable=True)
    quantity = Column(Integer, default=1)

    # Relationships
    wishlist = relationship("Wishlist", back_populates="items")
    product = relationship("Product", back_populates="wishlist_items")
    variant = relationship("ProductVariant", foreign_keys=[variant_id])

    @property
    def added_at(self):
        """Use created_at as added_at for compatibility"""
        return self.created_at
