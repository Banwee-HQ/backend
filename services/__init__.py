from .accounts import AuthService, UserService, AddressService, EmailService
from .catalog import ProductService, ReviewService, InventoryService, VariantTrackingService, RecommendationService
from .commerce import CartService, OrderService, PaymentService, RefundService, ShippingService, ShippingTrackingService, TaxService, PromocodeService, DiscountEngine, SubscriptionService, WebhookService, TransactionService
from .system import JinjaTemplateService, ValidationService, ContactMessageService

# Admin service functionality has been distributed to domain-specific services:
# - User management -> services/accounts/user.py (UserService)
# - Product management -> services/catalog/products.py (ProductService)
# - Order management -> services/commerce/orders.py (OrderService)
# - Refund management -> services/commerce/refunds.py (RefundService)
# - Subscription management -> services/commerce/subscriptions.py (SubscriptionService)
