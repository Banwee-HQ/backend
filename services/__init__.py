# Services package - Consolidated imports only

# Core services
from .auth import AuthService
from .cart import CartService
from .email import EmailService
from .products import ProductService
from .promocode import PromocodeService
from .review import ReviewService
from .search import SearchService
from .shipping import ShippingService
from .tax import TaxService
from .user import UserService, AddressService
from .tracking import VariantTrackingService
from .wishlist import WishlistService

# Consolidated services - single source of truth
from .orders import OrderService
from .subscriptions import SubscriptionService
from .payments import PaymentService
from .inventory import InventoryService
from .admin import AdminService
from .export import ExportService

# Utility services
from .templates import JinjaTemplateService

__all__ = [
    # Core services
    "AuthService",
    "CartService",
    "EmailService",
    "ProductService",
    "PromocodeService",
    "ReviewService",
    "SearchService",
    "ShippingService",
    "TaxService",
    "UserService",
    "AddressService",
    "VariantTrackingService",
    "WishlistService",
    # "BarcodeService",  # TODO: Implement barcode service
    
    # Consolidated services
    "OrderService",
    "SubscriptionService", 
    "PaymentService",
    "InventoryService",
    "AdminService",
    "ExportService",
    
    # Utility services
    "JinjaTemplateService",
]