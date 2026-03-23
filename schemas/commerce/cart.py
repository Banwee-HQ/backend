from pydantic import BaseModel, Field, ConfigDict, computed_field
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from schemas.product import ProductVariantResponse, ProductImageResponse


class AddToCartRequest(BaseModel):
    variant_id: UUID = Field(..., description="Product variant ID")
    quantity: int = Field(default=1, ge=1, description="Quantity must be at least 1")


class ApplyPromocodeRequest(BaseModel):
    code: str


class EnhancedProductVariantResponse(ProductVariantResponse):
    """Enhanced variant response for cart items with additional product details"""
    product_name: Optional[str] = None
    product_description: Optional[str] = None
    product_short_description: Optional[str] = None
    product_slug: Optional[str] = None
    product_category_id: Optional[str] = None
    product_rating_average: Optional[float] = None
    product_rating_count: Optional[int] = None
    product_is_featured: Optional[bool] = None
    product_specifications: Optional[Dict[str, Any]] = None
    product_dietary_tags: Optional[List[str]] = None
    product_tags: Optional[List[str]] = None
    product_origin: Optional[str] = None
    image_count: int = 0
    inventory_quantity_available: Optional[int] = None
    inventory_reorder_level: Optional[int] = None
    inventory_last_updated: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class CartItemResponse(BaseModel):
    id: UUID
    cart_id: UUID
    variant: EnhancedProductVariantResponse
    variant_id: UUID  # Add as regular field for easier access
    quantity: int
    price_per_unit: float
    total_price: float
    created_at: str = Field(..., description="ISO format datetime string")
    updated_at: Optional[str] = Field(None, description="ISO format datetime string")

    model_config = ConfigDict(from_attributes=True, json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class CartResponse(BaseModel):
    id: Optional[str] = None
    user_id: Optional[str] = None
    items: List[CartItemResponse]
    subtotal: float
    tax_amount: float
    shipping_amount: float
    total_amount: float
    currency: str = "USD"
    item_count: int = 0
    total_items: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    country_code: str = "US"
    province_code: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UpdateCartItemRequest(BaseModel):
    quantity: int


class CartValidationIssue(BaseModel):
    """Individual cart validation issue"""
    variant_id: Optional[str] = None
    issue: str = Field(..., description="Type of issue (e.g., 'out_of_stock', 'price_changed')")
    message: str = Field(..., description="Human-readable description of the issue")
    severity: str = Field(..., description="Severity level: 'error', 'warning', 'info'")
    
    # Optional fields for specific issue types
    current_stock: Optional[int] = None
    requested_quantity: Optional[int] = None
    adjusted_quantity: Optional[int] = None
    old_price: Optional[float] = None
    new_price: Optional[float] = None
    old_total: Optional[float] = None
    new_total: Optional[float] = None
    quantity: Optional[int] = None
    price_increased: Optional[bool] = None


class CartValidationSummary(BaseModel):
    """Summary of cart validation results"""
    total_items_checked: int
    valid_items: int
    removed_items: int
    price_updates: int
    stock_adjustments: int
    availability_issues: int
    cart_updated: bool


class CartValidationResponse(BaseModel):
    """Comprehensive cart validation response"""
    valid: bool = Field(..., description="Whether the cart passed validation")
    can_checkout: bool = Field(..., description="Whether the cart can proceed to checkout")
    cart: CartResponse = Field(..., description="Updated cart after validation")
    issues: List[CartValidationIssue] = Field(default=[], description="List of validation issues found")
    summary: CartValidationSummary = Field(..., description="Summary of validation results")
    validation_timestamp: str = Field(..., description="When validation was performed")
    error: Optional[str] = Field(None, description="Error message if validation failed")


class CheckoutValidationRequest(BaseModel):
    """Request for checkout validation"""
    shipping_address_id: UUID
    shipping_method_id: UUID  # Reverted back to UUID since we're using database shipping methods
    payment_method_id: UUID
    notes: Optional[str] = None


class EstimatedTotals(BaseModel):
    """Estimated order totals"""
    subtotal: float
    shipping_cost: float
    tax_amount: float
    tax_rate: float
    discount_amount: float
    total_amount: float


class CheckoutValidationResponse(BaseModel):
    """Response for checkout validation"""
    cart_validation: CartValidationResponse
    shipping_address_valid: bool
    shipping_method_valid: bool
    payment_method_valid: bool
    can_proceed: bool
    validation_errors: List[str] = Field(default=[])
    estimated_totals: Optional[EstimatedTotals] = None
