from core.db import Base

from .auth import User, Address
from .catalog import (
    Product, ProductVariant, ProductImage,
    Review, Inventory, WarehouseLocation, StockAdjustment,
    Wishlist, WishlistItem,
    VariantTrackingEntry, VariantPriceHistory, VariantAnalytics, VariantSubstitution,
)
from .commerce import (
    Cart, CartItem,
    Order, OrderItem, TrackingEvent,
    PaymentMethod, PaymentIntent, Transaction,
    Refund, RefundItem,
    ShippingMethod, ShipmentTracking, ShippingCarrier, ShipmentTrackingEvent,
    TaxRate, Promocode,
    Discount, SubscriptionDiscount, ProductRemovalAudit,
    Subscription, SubscriptionProduct,
)
from .admin import (
    PricingConfig, SubscriptionCostHistory, SubscriptionAnalytics, PaymentAnalytics,
    UserSession, AnalyticsEvent, ConversionFunnel, CustomerLifecycleMetrics,
)
from .system import (
    ContactMessage, MessageStatus, MessagePriority,
    TaxValidationRule, ShippingValidationRule,
)
