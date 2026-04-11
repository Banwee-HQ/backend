"""
Common service result types and TypedDicts for API responses
"""
from typing import TypedDict, Dict, Any, List, Optional
from decimal import Decimal
from datetime import date, datetime


# ============================================================================
# Cart Service Types
# ============================================================================

class CartValidationResult(TypedDict, total=False):
    """Result of cart validation with detailed information"""
    valid: bool
    can_checkout: bool
    cart: Optional[Any]  # Cart model
    issues: List[Dict[str, Any]]
    summary: Dict[str, Any]


# ============================================================================
# Order Service Types
# ============================================================================

class PricingCalculationResult(TypedDict, total=False):
    """Result of comprehensive pricing calculation"""
    subtotal: Decimal
    shipping_cost: Decimal
    tax_amount: Decimal
    tax_rate: float
    discount_amount: Decimal
    total_amount: Decimal
    currency: str
    breakdown: Dict[str, Any]


# ============================================================================
# Discount Service Types
# ============================================================================

class DiscountValidationResult(TypedDict, total=False):
    """Result of discount validation"""
    is_valid: bool
    error_message: Optional[str]
    discount: Optional[Any]  # Discount model


class DiscountCalculationResult(TypedDict, total=False):
    """Result of discount calculation"""
    discount_amount: Decimal
    final_total: Decimal
    discount_type: str


# ============================================================================
# Export Service Types
# ============================================================================

class ExportFilters(TypedDict, total=False):
    """Filters for export data"""
    start_date: Optional[date]
    end_date: Optional[date]
    customer_id: Optional[str]
    subscription_status: Optional[str]
    payment_status: Optional[str]
    variant_ids: Optional[List[str]]


class ExportResult(TypedDict, total=False):
    """Result of export operation"""
    content: bytes
    content_type: str
    filename: str
    format_type: str
    generated_at: datetime


# ============================================================================
# Template Service Types
# ============================================================================

class RenderedTemplate(TypedDict, total=False):
    """Result of template rendering"""
    content: str
    template_name: str
    context_used: Dict[str, Any]
    rendered_at: str


class RenderedExport(TypedDict, total=False):
    """Result of export template rendering"""
    content: str
    format_type: str
    template_name: str
    data_used: Dict[str, Any]
    rendered_at: str


class TemplateValidationResult(TypedDict, total=False):
    """Result of template validation"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
