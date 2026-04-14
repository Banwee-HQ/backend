from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from uuid import UUID

from models.catalog.product import ProductStatus, AvailabilityStatus

def normalize_dietary_tags(value):
    """Normalize dietary_tags to always be a dict, handling both list and dict inputs."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        # Convert list to dict with True values
        return {tag: True for tag in value}
    return {}


class ImageResponse(BaseModel):
    id: UUID
    variant_id: UUID
    url: str
    alt_text: Optional[str]
    is_primary: bool
    sort_order: int
    format: Optional[str]
    created_at: str

    model_config = ConfigDict(from_attributes=True, json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class VariantCreate(BaseModel):
    sku: Optional[str] = None  # Optional - will be auto-generated if not provided
    name: str
    base_price: float
    sale_price: Optional[float] = None
    stock: int = 0
    attributes: Optional[Dict[str, Any]] = {}
    specifications: Optional[Dict[str, Any]] = None
    dietary_tags: Optional[Dict[str, Any]] = {}
    tags: Optional[str] = None
    availability_status: str = "available"
    image_urls: Optional[List[str]] = []  # jsDelivr CDN URLs

    @field_validator('dietary_tags', mode='before')
    @classmethod
    def validate_dietary_tags(cls, v):
        return normalize_dietary_tags(v)


class Create(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    short_description: Optional[str] = None
    category: str
    variants: Optional[List[VariantCreate]] = None
    origin: Optional[str] = None
    is_featured: bool = False
    is_bestseller: bool = False
    # Flat fields for simple product creation (auto-creates a default variant)
    base_price: Optional[float] = None
    sale_price: Optional[float] = None
    cost_price: Optional[float] = None
    quantity: Optional[int] = 0
    sku: Optional[str] = None
    weight_kg: Optional[float] = None
    tags: Optional[List[str]] = []
    origin_country: Optional[str] = None
    is_active: Optional[bool] = True


class VariantUpdate(BaseModel):
    id: Optional[UUID] = None  # Include ID for existing variants
    sku: Optional[str] = None
    name: Optional[str] = None
    base_price: Optional[float] = None
    sale_price: Optional[float] = None
    stock: Optional[int] = None
    attributes: Optional[Dict[str, Any]] = None
    specifications: Optional[Dict[str, Any]] = None
    dietary_tags: Optional[Dict[str, Any]] = None
    tags: Optional[str] = None
    is_active: Optional[bool] = None
    availability_status: Optional[AvailabilityStatus] = None
    images: Optional[List[Dict[str, Any]]] = None  # List of image objects with id, url, alt_text, is_primary, sort_order

    @field_validator('dietary_tags', mode='before')
    @classmethod
    def validate_dietary_tags(cls, v):
        return normalize_dietary_tags(v)


class Update(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    category: Optional[str] = None
    origin: Optional[str] = None
    product_status: Optional[ProductStatus] = None
    is_featured: Optional[bool] = None
    is_bestseller: Optional[bool] = None
    variants: Optional[List[VariantUpdate]] = None


class InventoryResponse(BaseModel):
    id: Optional[UUID] = None
    quantity_available: int = 0
    low_stock_threshold: int = 10
    inventory_status: str = "active"

    model_config = ConfigDict(from_attributes=True)


class VariantResponse(BaseModel):
    id: UUID
    product_id: UUID
    sku: str
    name: str
    base_price: float
    sale_price: Optional[float]
    current_price: float
    discount_percentage: float
    stock: int
    attributes: Optional[Dict[str, Any]]
    specifications: Optional[Dict[str, Any]] = None
    dietary_tags: Optional[Dict[str, Any]] = {}
    tags: List[str] = []
    availability_status: AvailabilityStatus = AvailabilityStatus.AVAILABLE
    view_count: int = 0
    purchase_count: int = 0
    is_active: bool
    images: List[ImageResponse] = []
    primary_image: Optional[ImageResponse] = None
    inventory: Optional[InventoryResponse] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    product_name: Optional[str] = None
    product_description: Optional[str] = None

    @field_validator('dietary_tags', mode='before')
    @classmethod
    def validate_dietary_tags(cls, v):
        return normalize_dietary_tags(v)

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None
        }
    )


class PriceRange(BaseModel):
    min: float
    max: float


class Response(BaseModel):
    id: UUID
    name: str
    slug: Optional[str] = None
    description: Optional[str]
    category: Optional[str] = None
    is_featured: bool = False
    is_bestseller: bool = False
    rating: float
    review_count: int
    origin: Optional[str]
    is_active: bool
    price_range: PriceRange
    in_stock: bool
    availability_status: AvailabilityStatus = AvailabilityStatus.AVAILABLE
    created_at: datetime
    updated_at: Optional[datetime] = None
    # Relationships
    variants: List[VariantResponse] = []
    primary_variant: Optional[VariantResponse] = None

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None
        }
    )


class ListResponse(BaseModel):
    products: List[Response]
    total: int
    page: int
    per_page: int
    pages: int


class DetailResponse(Response):
    # Includes all product fields plus additional details
    pass


# Product image schemas
class ImageCreate(BaseModel):
    url: str
    alt_text: Optional[str] = None
    is_primary: bool = False
    sort_order: int = 0


class ImageUpdate(BaseModel):
    url: Optional[str] = None
    alt_text: Optional[str] = None
    is_primary: Optional[bool] = None


# Admin product management schemas
class ProductPatch(BaseModel):
    """Request model for partial product updates via PATCH."""
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    compare_at_price: Optional[float] = None
    category: Optional[str] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None
    tags: Optional[list] = None
    seo_title: Optional[str] = None


class VariantStockUpdate(BaseModel):
    """Request model for updating variant stock."""
    quantity: int
    reason: Optional[str] = None


class ProductModeration(BaseModel):
    """Request model for product moderation."""
    action: str  # "approve" or "reject"
    reason: Optional[str] = None


class ProductFeatureToggle(BaseModel):
    """Request model for toggling product featured status."""
    featured: bool
