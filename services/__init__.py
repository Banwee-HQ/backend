from .accounts import AuthService, UserService, AddressService, EmailService
from .catalog import ProductService, ReviewService, InventoryService, RecommendationService
from .commerce import CartService, OrderService, PaymentService, RefundService, ShippingService, CarrierService, ShippingTrackingService, TaxService, PromocodeService, DiscountEngine, SubscriptionService, WebhookService
from .system import JinjaTemplateService, ContactMessageService

# Admin service functionality has been distributed to domain-specific services:
# - User management -> services/accounts/user.py (UserService)
# - Product management -> services/catalog/products.py (ProductService)
# - Order management -> services/commerce/orders.py (OrderService)
# - Refund management -> services/commerce/refunds.py (RefundService)
# - Subscription management -> services/commerce/subscriptions.py (SubscriptionService)
