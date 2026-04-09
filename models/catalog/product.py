"""
Optimized product models with strategic JSON usage
"""
from sqlalchemy import Column, String, ForeignKey, DateTime, Float, Boolean, Text, Integer, func, Index, JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column
from core.db import Base, CHAR_LENGTH, GUID
from core.utils.uuid_utils import uuid7
from datetime import datetime
from typing import Dict, Any, Optional
import uuid


class Product(Base):
    """Optimized product model with hard delete only and strategic JSON usage"""
    __tablename__ = "products"
    __table_args__ = (
        # Optimized indexes for product queries
        Index('idx_products_category_status', 'category', 'product_status'),
        Index('idx_products_published', 'published_at', 'product_status'),
        Index('idx_products_slug', 'slug'),
        {'schema': 'catalog'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Core product information as columns for performance
    name: Mapped[str] = mapped_column(String(CHAR_LENGTH))
    slug: Mapped[str] = mapped_column(String(CHAR_LENGTH), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    short_description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Category as string field
    category: Mapped[str] = mapped_column(String(100))

    # Status fields as columns for indexing and fast filtering
    product_status: Mapped[str] = mapped_column(String(50), default="active")  # active, inactive, draft, discontinued

    # Quality metrics as columns for sorting/filtering (aggregated from variants)
    rating_average: Mapped[float] = mapped_column(Float, default=0.0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)

    # Marketing flags as columns for fast filtering
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    is_bestseller: Mapped[bool] = mapped_column(Boolean, default=False)

    # Dates for lifecycle management
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships with optimized lazy loading
    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan", lazy="selectin")
    reviews = relationship("Review", back_populates="product", lazy="select")
    wishlist_items = relationship("WishlistItem", back_populates="product", lazy="select")
    cart_items = relationship("CartItem", back_populates="product", lazy="select")

    # Product metadata as JSON columns for querying (cross-platform compatible)
    product_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    @property
    def is_active(self) -> bool:
        """Compatibility property — True when product_status is 'active'."""
        return self.product_status == "active"

    @property
    def primary_variant(self):
        """Get the primary variant (first one or cheapest)"""
        if not self.variants:
            return None
        return min(self.variants, key=lambda v: v.base_price)

    @property
    def price_range(self) -> dict:
        """Get min and max price from variants"""
        if not self.variants:
            return {"min": 0, "max": 0}

        prices = [v.sale_price or v.base_price for v in self.variants if v.is_active]
        if not prices:
            return {"min": 0, "max": 0}

        return {"min": min(prices), "max": max(prices)}

    @property
    def in_stock(self) -> bool:
        """Check if any variant is in stock"""
        return any(v.inventory and v.inventory.quantity_available > 0 for v in self.variants if v.is_active)

    @property
    def availability_status(self) -> str:
        """Get overall availability status from variants"""
        if not self.variants:
            return "out_of_stock"
        
        # Check if any variant is available
        available_variants = [v for v in self.variants if v.is_active]
        if not available_variants:
            return "out_of_stock"
        
        # Check stock levels
        in_stock = [v for v in available_variants if v.inventory and v.inventory.quantity_available > 0]
        low_stock = [v for v in available_variants if v.inventory and v.inventory.quantity_available > 0 and v.inventory.quantity_available <= v.inventory.low_stock_threshold]
        
        if in_stock:
            return "limited" if low_stock else "available"
        return "out_of_stock"

    def to_dict(self, include_variants=False, include_seo=False) -> dict:
        """Convert product to dictionary for API responses"""
        data = {
            "id": str(self.id),
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "short_description": self.short_description,
            "category": self.category,
            "product_status": self.product_status,
            "rating_average": self.rating_average,
            "rating_count": self.rating_count,
            "review_count": self.review_count,
            "is_featured": self.is_featured,
            "is_bestseller": self.is_bestseller,
            "price_range": self.price_range,
            "availability_status": self.availability_status,
            "in_stock": self.in_stock,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "product_metadata": self.product_metadata,
        }

        if include_variants:
            data["variants"] = [v.to_dict() for v in self.variants]

        if include_seo:
            data["seo"] = {
                "meta_title": self.meta_title,
                "meta_description": self.meta_description,
                "canonical_url": f"https://www.banwee.com/products/{self.slug}",
                "og_image": self.primary_variant.primary_image.url if self.primary_variant and self.primary_variant.primary_image else None,
            }

        return data


class ProductVariant(Base):
    """Product variants with hard delete only"""
    __tablename__ = "product_variants"
    __table_args__ = (
        Index('idx_variants_product_id', 'product_id'),
        Index('idx_variants_sku', 'sku'),
        Index('idx_variants_active', 'is_active'),
        Index('idx_variants_price', 'base_price', 'sale_price'),
        Index('idx_variants_availability', 'availability_status'),
        # GIN indexes for JSON fields only
        Index('idx_variants_specifications', 'specifications', postgresql_using='gin'),
        Index('idx_variants_dietary_tags', 'dietary_tags', postgresql_using='gin'),
        {'schema': 'catalog'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    product_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("products.id"))
    sku: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(CHAR_LENGTH))

    # Pricing as columns
    base_price: Mapped[float] = mapped_column(Float)
    sale_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Use JSON only for complex attributes that need querying
    attributes: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)    # Flexible metadata as JSON columns for querying (cross-platform compatible)
    specifications: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Technical specs that need filtering
    dietary_tags: Mapped[dict] = mapped_column(JSON, default=dict)  # Dietary information for filtering

    # Simple tags as text for better performance
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # "organic,gluten-free,vegan"

    # Status as column
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    availability_status: Mapped[str] = mapped_column(String(50), default="available")  # available, limited, out_of_stock

    # Analytics as columns
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    purchase_count: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    product = relationship("Product", back_populates="variants")
    images = relationship("ProductImage", back_populates="variant", cascade="all, delete-orphan", lazy="selectin")
    cart_items = relationship("CartItem", back_populates="variant", lazy="select")
    order_items = relationship("OrderItem", back_populates="variant", lazy="select")
    inventory = relationship("Inventory", uselist=False, back_populates="variant", cascade="all, delete-orphan", lazy="selectin")
    
    # Variant tracking relationships
    tracking_entries = relationship("VariantTrackingEntry", back_populates="variant", lazy="select")
    price_history = relationship("VariantPriceHistory", back_populates="variant", lazy="select")
    analytics = relationship("VariantAnalytics", back_populates="variant", lazy="select")

    @property
    def current_price(self) -> float:
        """Get current price (sale price if available, otherwise base price)"""
        return self.sale_price if self.sale_price else self.base_price

    @property
    def stock(self) -> int:
        """Get available stock quantity"""
        return self.inventory.quantity_available if self.inventory else 0

    @property
    def discount_percentage(self) -> float:
        """Calculate discount percentage if on sale"""
        if not self.sale_price or self.sale_price >= self.base_price:
            return 0
        return round(((self.base_price - self.sale_price) / self.base_price) * 100, 2)

    @property
    def primary_image(self):
        """Get primary image"""
        return next((img for img in self.images if img.is_primary),
                    self.images[0] if self.images else None)

    def to_dict(self, include_images=True, include_product=False) -> dict:
        """Convert variant to dictionary for API responses"""
        data = {
            "id": str(self.id),
            "product_id": str(self.product_id),
            "sku": self.sku,
            "name": self.name,
            "base_price": self.base_price,
            "sale_price": self.sale_price,
            "current_price": self.current_price,
            "discount_percentage": self.discount_percentage,
            "attributes": self.attributes,
            "specifications": self.specifications,
            "dietary_tags": self.dietary_tags,
            "tags": self.tags.split(",") if self.tags else [],
            "is_active": self.is_active,
            "availability_status": self.availability_status,
            "view_count": self.view_count,
            "purchase_count": self.purchase_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "inventory": {
                "id": str(self.inventory.id) if self.inventory else None,
                "quantity_available": self.inventory.quantity_available if self.inventory else 0,
                "low_stock_threshold": self.inventory.low_stock_threshold if self.inventory else 10,
                "inventory_status": self.inventory.inventory_status if self.inventory else "active"
            } if self.inventory else None
        }

        if include_images:
            data["images"] = [img.to_dict() for img in self.images]
            data["primary_image"] = self.primary_image.to_dict() if self.primary_image else None

        if include_product and self.product:
            data["product_name"] = self.product.name
            data["product_description"] = self.product.description

        return data


class ProductImage(Base):
    """Product images - no soft delete needed"""
    __tablename__ = "product_images"
    __table_args__ = (
        Index('idx_images_variant_id', 'variant_id'),
        Index('idx_images_primary', 'is_primary'),
        {'schema': 'catalog'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    variant_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("product_variants.id"))
    url: Mapped[str] = mapped_column(String(500))
    alt_text: Mapped[Optional[str]] = mapped_column(String(CHAR_LENGTH), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    format: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # jpg, png, webp

    # Relationships
    variant = relationship("ProductVariant", back_populates="images")

    def to_dict(self) -> dict:
        """Convert image to dictionary for API responses"""
        return {
            "id": str(self.id),
            "variant_id": str(self.variant_id),
            "url": self.url,
            "alt_text": self.alt_text,
            "is_primary": self.is_primary,
            "sort_order": self.sort_order,
            "format": self.format,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }