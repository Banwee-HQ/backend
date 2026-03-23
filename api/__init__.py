from .auth import auth_router, oauth_router, user_router
from .catalog import products_router, categories_router, search_router, review_router, inventory_router, wishlist_router
from .commerce import cart_router, orders_router, payments_router, refunds_router, shipping_router, shipping_tracking_router, tax_router, promocodes_router, subscriptions_router, webhooks_router
from .admin import admin_router, analytics_router
from .system import health_router, contact_messages_router

__all__ = [
    "auth_router", "oauth_router", "user_router",
    "products_router", "categories_router", "search_router", "review_router", "inventory_router", "wishlist_router",
    "cart_router", "orders_router", "payments_router", "refunds_router", "shipping_router", "shipping_tracking_router", "tax_router", "promocodes_router", "subscriptions_router", "webhooks_router",
    "admin_router", "analytics_router",
    "health_router", "contact_messages_router",
]
