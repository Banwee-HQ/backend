# Models package - Consolidated imports only
from core.db import Base
from .user import User, Address
from .product import Product, ProductVariant, ProductImage, Category
from .cart import Cart, CartItem
from .review import Review
from .promocode import Promocode
from .shipping import ShippingMethod
from .wishlist import Wishlist, WishlistItem
from .analytics import UserSession, AnalyticsEvent, ConversionFunnel, CustomerLifecycleMetrics
from .refunds import Refund, RefundItem
from .tax_rates import TaxRate
from .shipping_tracking import ShipmentTracking, ShippingCarrier,ShipmentTrackingEvent
from .contact_message import ContactMessage, MessageStatus, MessagePriority

# Consolidated models - single source of truth
from .orders import Order, OrderItem, TrackingEvent
from .subscriptions import Subscription, SubscriptionProduct
from .payments import PaymentMethod, PaymentIntent, Transaction
from .inventories import WarehouseLocation, Inventory, StockAdjustment
from .admin import PricingConfig, SubscriptionCostHistory, SubscriptionAnalytics, PaymentAnalytics
from .discounts import Discount, SubscriptionDiscount, ProductRemovalAudit
from .validation_rules import TaxValidationRule, ShippingValidationRule
from .variant_tracking import VariantTrackingEntry, VariantPriceHistory, VariantAnalytics, VariantSubstitution

# Import utils if they exist
try:
    from .utils import ModelUtils
except ImportError:
    pass

__all__ = [
    # User models
    "User",
    "Address",

    # Product models
    "Product",
    "ProductVariant",
    "ProductImage",
    "Category",

    # Cart models
    "Cart",
    "CartItem",

    # Order models (consolidated)
    "Order",
    "OrderItem",
    "TrackingEvent",

    # Subscription models (consolidated)
    "Subscription",
    "SubscriptionProduct",

    # Discount models
    "Discount",
    "SubscriptionDiscount",
    "ProductRemovalAudit",

    # Validation models
    "TaxValidationRule",
    "ShippingValidationRule",

    # Payment models (consolidated)
    "PaymentMethod",
    "PaymentIntent",
    "Transaction",

    # Inventory models (consolidated)
    "WarehouseLocation",
    "Inventory",
    "StockAdjustment",

    # Admin models (consolidated)
    "PricingConfig",
    "SubscriptionCostHistory",
    "SubscriptionAnalytics",
    "PaymentAnalytics",

    # Content models
    "Review",

    # Commerce models
    "Promocode",
    "ShippingMethod",

    # Wishlist models
    "Wishlist",
    "WishlistItem",
    
    # Variant tracking models
    "VariantTrackingEntry",
    "VariantPriceHistory",
    "VariantAnalytics",
    "VariantSubstitution",
    
    # Analytics models
    "UserSession",
    "AnalyticsEvent",
    "ConversionFunnel",
    "CustomerLifecycleMetrics",
    
    # Refund models
    "Refund",
    "RefundItem",
    
    # Tax models
    "TaxRate",
    
    # Shipping tracking models
    "ShipmentTracking", 
    "ShippingCarrier",
    "ShipmentTrackingEvent",
    
    # Contact message models
    "ContactMessage",
    "MessageStatus",
    "MessagePriority"
]
