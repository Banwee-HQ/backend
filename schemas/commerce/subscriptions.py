"""Subscription schemas"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

from models.commerce.subscriptions import SubscriptionStatus, BillingCycle, DeliveryType


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
    discount_type: str  # "percentage" or "fixed"
    value: float
    code: Optional[str] = None


class Create(BaseModel):
    """Create subscription"""
    name: Optional[str] = "My Subscription"
    variant_ids: Optional[List[str]] = []
    variant_quantities: Optional[Dict[str, int]] = {}
    delivery_type: DeliveryType = DeliveryType.STANDARD
    delivery_address_id: Optional[UUID] = None
    billing_cycle: BillingCycle = BillingCycle.MONTHLY
    currency: str = "USD"
    discount_code: Optional[str] = None
    # Accept plan_id for compatibility with tests
    plan_id: Optional[str] = None
    payment_method_id: Optional[str] = None


class Update(BaseModel):
    """Update subscription"""
    name: Optional[str] = None
    delivery_type: Optional[DeliveryType] = None
    delivery_address_id: Optional[UUID] = None
    auto_renew: Optional[bool] = None
    variant_ids: Optional[List[str]] = None
    variant_quantities: Optional[Dict[str, int]] = None


class CostCalculation(BaseModel):
    """Request to calculate subscription cost"""
    variant_ids: List[str]
    variant_quantities: Optional[Dict[str, int]] = {}
    delivery_type: DeliveryType = DeliveryType.STANDARD
    delivery_address_id: Optional[UUID] = None
    currency: str = "USD"


class AddProducts(BaseModel):
    """Add products to subscription"""
    variant_ids: List[str]
    variant_quantities: Optional[Dict[str, int]] = {}


class RemoveProducts(BaseModel):
    """Remove products from subscription"""
    variant_ids: List[str]


class UpdateQuantity(BaseModel):
    """Update variant quantity in subscription"""
    variant_id: str
    quantity: int = Field(gt=0, description="New quantity (must be greater than 0)")


class QuantityChange(BaseModel):
    """Change variant quantity (increment/decrement)"""
    variant_id: str
    change: int = Field(description="Quantity change (positive to add, negative to subtract)")


class DiscountApplication(BaseModel):
    """Apply discount to subscription"""
    discount_code: str


class Response(BaseModel):
    """Subscription response"""
    id: str
    user_id: str
    name: str
    status: SubscriptionStatus
    currency: str
    billing_cycle: BillingCycle
    auto_renew: bool
    next_billing_date: Optional[datetime]
    delivery_type: Optional[DeliveryType]
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
    
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None
        }
    )

