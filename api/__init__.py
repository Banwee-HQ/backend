# Consolidated route imports
from .admin import router as admin_router
from .analytics import router as analytics_router 
from .auth import router as auth_router
from .cart import router as cart_router
from .categories import router as categories_router
from .health import router as health_router
from .inventory import router as inventory_router
from .oauth import router as oauth_router
from .orders import router as orders_router
from .payments import router as payments_router
from .promocodes import router as promocodes_router
from .products import router as products_router
from .refunds import router as refunds_router
from .review import router as review_router
from .search import router as search_router
from .shipping import router as shipping_router
from .subscriptions import router as subscriptions_router
from .tax import router as tax_router
from .user import router as user_router
from .webhooks import router as webhooks_router
from .wishlist import router as wishlist_router

# Export all routers for easy importing
__all__ = [
    "admin_router",
    "analytics_router",
    "auth_router",
    "cart_router",
    "categories_router",
    "health_router",
    "inventory_router",
    "oauth_router",
    "orders_router",
    "payments_router",
    "products_router",
    "promocodes_router",
    "refunds_router",
    "review_router",
    "search_router",
    "shipping_router",
    "subscriptions_router",
    "tax_router",
    "user_router",
    "webhooks_router",
    "wishlist_router",
]

