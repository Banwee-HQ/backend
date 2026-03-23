from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


class ProductImageResponse(BaseModel):
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


class ProductVariantCreate(BaseModel):
    sku: Optional[str] = None  # Optional - will be auto-generated if not provided
    name: str
    base_price: float
    sale_price: Optional[float] = None
    stock: int = 0
    attributes: Optional[Dict[str, Any]] = {}
    specifications: Optional[Dict[str, Any]] = None
    dietary_tags: Optional[List[str]] = []
    tags: Optional[str] = None
    availability_status: str = "available"
    image_urls: Optional[List[str]] = []  # jsDelivr CDN URLs


class ProductCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    short_description: Optional[str] = None
    category_id: UUID
    variants: List[ProductVariantCreate]
    origin: Optional[str] = None
    is_featured: bool = False
    is_bestseller: bool = False


class ProductVariantUpdate(BaseModel):
    id: Optional[UUID] = None  # Include ID for existing variants
    sku: Optional[str] = None
    name: Optional[str] = None
    base_price: Optional[float] = None
    sale_price: Optional[float] = None
    stock: Optional[int] = None
    attributes: Optional[Dict[str, Any]] = None
    specifications: Optional[Dict[str, Any]] = None
    dietary_tags: Optional[List[str]] = None
    tags: Optional[str] = None
    is_active: Optional[bool] = None
    availability_status: Optional[str] = None
    barcode: Optional[str] = None
    qr_code: Optional[str] = None
    images: Optional[List[Dict[str, Any]]] = None  # List of image objects with id, url, alt_text, is_primary, sort_order


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    category_id: Optional[UUID] = None
    origin: Optional[str] = None
    product_status: Optional[str] = None
    is_featured: Optional[bool] = None
    is_bestseller: Optional[bool] = None
    variants: Optional[List[ProductVariantUpdate]] = None


class CategoryResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    image_url: Optional[str]
    is_active: bool
    product_count: int = 0
    created_at: str
    updated_at: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class SupplierResponse(BaseModel):
    id: UUID
    email: str
    firstname: str
    lastname: str
    phone: Optional[str]
    role: str

    model_config = ConfigDict(from_attributes=True)


class InventoryResponse(BaseModel):
    id: Optional[UUID] = None
    quantity_available: int = 0
    low_stock_threshold: int = 10
    inventory_status: str = "active"

    model_config = ConfigDict(from_attributes=True)


class ProductVariantResponse(BaseModel):
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
    dietary_tags: Optional[List[str]] = []
    tags: List[str] = []
    availability_status: str = "available"
    view_count: int = 0
    purchase_count: int = 0
    is_active: bool
    barcode: Optional[str] = None  # Base64 encoded barcode image
    qr_code: Optional[str] = None  # Base64 encoded QR code image
    images: List[ProductImageResponse] = []
    primary_image: Optional[ProductImageResponse] = None
    inventory: Optional[InventoryResponse] = None
    created_at: str
    updated_at: Optional[str]
    product_name: Optional[str] = None
    product_description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class PriceRange(BaseModel):
    min: float
    max: float


class ProductResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    category_id: UUID
    supplier_id: UUID
    featured: bool
    rating: float
    review_count: int
    origin: Optional[str]
    is_active: bool
    price_range: PriceRange
    in_stock: bool
    availability_status: str = "available"
    created_at: str
    updated_at: Optional[str]
    # Relationships
    category: Optional[CategoryResponse] = None
    supplier: Optional[SupplierResponse] = None
    variants: List[ProductVariantResponse] = []
    primary_variant: Optional[ProductVariantResponse] = None

    model_config = ConfigDict(from_attributes=True)


class ProductListResponse(BaseModel):
    products: List[ProductResponse]
    total: int
    page: int
    per_page: int
    pages: int


class ProductDetailResponse(ProductResponse):
    # Includes all product fields plus additional details
    pass


class BarcodeGenerateRequest(BaseModel):
    """Request model for generating barcode/QR code"""
    variant_id: UUID


class BarcodeResponse(BaseModel):
    """Response model for barcode/QR code generation"""
    variant_id: UUID
    barcode: Optional[str] = None
    qr_code: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class BarcodeUpdateRequest(BaseModel):
    """Request model for updating barcode/QR code"""
    barcode: Optional[str] = None
    qr_code: Optional[str] = None
