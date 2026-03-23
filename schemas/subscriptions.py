"""Subscription schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


class VariantItem(BaseModel):
    """Variant with quantity"""
    id: str
    qty: int = 1


class VariantPrice(BaseModel):
    """Variant with price and quantity"""
    id: str
    price: float
    qty: int = 1


class DiscountInfo(BaseModel):
    """Discount information"""
    type: str  # "percentage" or "fixed"
    value: float
    code: Optional[str] = None


class CreateSubscription(BaseModel):
    """Create subscription"""
    name: str
    variant_ids: List[str]
    variant_quantities: Optional[Dict[str, int]] = {}
    delivery_type: str = "standard"
    delivery_address_id: Optional[UUID] = None
    billing_cycle: str = "monthly"
    currency: str = "USD"
    discount_code: Optional[str] = None


class UpdateSubscription(BaseModel):
    """Update subscription"""
    name: Optional[str] = None
    delivery_type: Optional[str] = None
    delivery_address_id: Optional[UUID] = None
    auto_renew: Optional[bool] = None
    variant_ids: Optional[List[str]] = None
    variant_quantities: Optional[Dict[str, int]] = None


class SubscriptionCostCalculationRequest(BaseModel):
    """Request to calculate subscription cost"""
    variant_ids: List[str]
    variant_quantities: Optional[Dict[str, int]] = {}
    delivery_type: str = "standard"
    delivery_address_id: Optional[UUID] = None
    currency: str = "USD"


class SubscriptionAddProducts(BaseModel):
    """Add products to subscription"""
    variant_ids: List[str]
    variant_quantities: Optional[Dict[str, int]] = {}


class SubscriptionRemoveProducts(BaseModel):
    """Remove products from subscription"""
    variant_ids: List[str]


class SubscriptionUpdateQuantity(BaseModel):
    """Update variant quantity in subscription"""
    variant_id: str
    quantity: int = Field(gt=0, description="New quantity (must be greater than 0)")


class SubscriptionQuantityChange(BaseModel):
    """Change variant quantity (increment/decrement)"""
    variant_id: str
    change: int = Field(description="Quantity change (positive to add, negative to subtract)")


class DiscountApplicationRequest(BaseModel):
    """Apply discount to subscription"""
    discount_code: str


class SubscriptionResponse(BaseModel):
    """Subscription response"""
    id: str
    user_id: str
    name: str
    status: str
    currency: str
    billing_cycle: str
    auto_renew: bool
    next_billing_date: Optional[str]
    delivery_type: Optional[str]
    delivery_address_id: Optional[str]
    
    # At-creation prices
    price_at_creation: Optional[float]
    variant_prices_at_creation: Optional[List[Dict[str, Any]]]
    shipping_amount_at_creation: Optional[float]
    tax_amount_at_creation: Optional[float]
    
    # Current prices
    current_variant_prices: Optional[List[Dict[str, Any]]]
    current_shipping_amount: Optional[float]
    current_tax_amount: Optional[float]
    
    # Discount
    discount: Optional[Dict[str, Any]]
    
    # Products
    products: Optional[List[Dict[str, Any]]] = []
    
    created_at: Optional[str]
    updated_at: Optional[str]

    class Config:
        from_attributes = True

