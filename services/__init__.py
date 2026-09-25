from .accounts import AuthService, UserService, AddressService, EmailService
from .catalog import ProductService, ReviewService, InventoryService, RecommendationService
from .commerce import CartService, OrderService, PaymentService, RefundService, ShippingService, CarrierService, ShippingTrackingService, TaxService, PromocodeService, SubscriptionService, WebhookService
from .system import JinjaTemplateService, ContactMessageService

# Admin service functionality lives in its domain-specific service (e.g. UserService,
# ProductService, OrderService) rather than grouped here.
