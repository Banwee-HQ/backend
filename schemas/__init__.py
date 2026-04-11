from .accounts import *
from .catalog import *
from .commerce import *
from .system import *

# Admin schemas have been distributed to domain-specific schema modules:
# - User admin schemas -> schemas/accounts/user.py (AdminUserUpdate, UserStatusUpdate)
# - Product admin schemas -> schemas/catalog/product.py (ProductPatch, VariantStockUpdate, ProductModeration, ProductFeatureToggle)
# - Order admin schemas -> schemas/commerce/orders.py (ShipOrder, UpdateOrderStatus, OrderPatch)
# - Refund admin schemas -> schemas/commerce/refunds.py (UpdateRefundStatus, RefundPatch)
# - Tax admin schemas -> schemas/commerce/tax.py (RateCreate, RateUpdate, RateResponse)
