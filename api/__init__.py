from .accounts import (
    auth_router, oauth_router, user_router, addresses_router, oauth_social_router
)
from .catalog import products_router, review_router, inventory_router, wishlist_router
from .commerce import cart_router, orders_router, payments_router, refunds_router, shipping_router, shipping_tracking_router, tax_router, promocodes_router, subscriptions_router, webhooks_router
from .analytics import analytics_router
from .system import health_router, contact_messages_router

# Admin functionality has been distributed to domain-specific modules:
# - accounts/user.py for user management
# - catalog/products.py for product management
# - commerce/orders.py for order management
# - commerce/refunds.py for refund management
# - commerce/subscriptions.py for subscription management
# - commerce/tax.py for tax rate management
#
# The analytics module contains analytics and reporting endpoints.

__all__ = [
    "auth_router", "oauth_router", "oauth_social_router", "user_router", "addresses_router",
    "products_router", "review_router", "inventory_router", "wishlist_router",
    "cart_router", "orders_router", "payments_router", "refunds_router", "shipping_router", "shipping_tracking_router", "tax_router", "promocodes_router", "subscriptions_router", "webhooks_router",
    "analytics_router",
    "health_router", "contact_messages_router",
]
