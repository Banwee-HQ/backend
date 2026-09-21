"""
Comprehensive Order Service with Advanced Pricing and Security
Handles complete order lifecycle with backend-only price calculations
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, delete, String
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, BackgroundTasks
from models.commerce.orders import Order, OrderItem, TrackingEvent, PaymentStatus, OrderStatus, FulfillmentStatus, OrderSource
from models.accounts.user import User
from services.accounts.email import EmailService
from models.commerce.cart import Cart, CartItem
from models.accounts.user import User, Address
from models.catalog.product import ProductVariant
from models.commerce.shipping import ShippingMethod
from models.commerce.payments import PaymentMethod
from models.commerce.tax_rates import TaxRate
from schemas.commerce.orders import Response as OrderResponse, ItemResponse as OrderItemResponse, Checkout as CheckoutRequest
from schemas.catalog.inventory import AdjustmentCreate as StockAdjustmentCreate
from services.commerce.cart import CartService
from services.commerce.payments import PaymentService
from services.catalog.inventory import InventoryService 
from services.commerce.tax import TaxService
from services.commerce.shipping import ShippingService
from services.commerce.discounts import DiscountEngine
from models.commerce.discounts import DiscountType
from services.commerce.promocode import PromocodeService
from models.catalog.inventories import Inventory
from uuid import UUID
from core.utils.uuid_utils import uuid7
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
from decimal import Decimal, ROUND_HALF_UP
from core.config import settings
from core.logging import get_structured_logger

from schemas.common.service_types import PricingCalculationResult

logger = get_structured_logger(__name__)


def get_currency_from_address(country: str) -> str:
    """Determine currency based on country in address."""
    if not country:
        return "USD"
    
    country = country.upper()
    
    # Map countries to their currencies (both codes and full names)
    country_to_currency = {
        # North America
        "CA": "CAD", "CANADA": "CAD",
        "US": "USD", "UNITED STATES": "USD", "USA": "USD",
        "MX": "MXN", "MEXICO": "MXN",
        "GT": "GTQ", "GUATEMALA": "GTQ",
        "CR": "CRC", "COSTA RICA": "CRC",
        "PA": "PAB", "PANAMA": "PAB",
        "JM": "JMD", "JAMAICA": "JMD",
        "DO": "DOP", "DOMINICAN REPUBLIC": "DOP",
        "CU": "CUP", "CUBA": "CUP",
        "HT": "HTG", "HAITI": "HTG",
        "HN": "HNL", "HONDURAS": "HNL",
        "NI": "NIO", "NICARAGUA": "NIO",
        "SV": "SVC", "EL SALVADOR": "SVC",
        "BB": "BBD", "BARBADOS": "BBD",
        "BS": "BSD", "BAHAMAS": "BSD",
        "TT": "TTD", "TRINIDAD AND TOBAGO": "TTD",
        
        # Central America
        "BZ": "BZD", "BELIZE": "BZD",
        
        # Europe (Eurozone)
        "DE": "EUR", "GERMANY": "EUR",
        "FR": "EUR", "FRANCE": "EUR",
        "IT": "EUR", "ITALY": "EUR",
        "ES": "EUR", "SPAIN": "EUR",
        "NL": "EUR", "NETHERLANDS": "EUR",
        "BE": "EUR", "BELGIUM": "EUR",
        "AT": "EUR", "AUSTRIA": "EUR",
        "IE": "EUR", "IRELAND": "EUR",
        "PT": "EUR", "PORTUGAL": "EUR",
        "FI": "EUR", "FINLAND": "EUR",
        "GR": "EUR", "GREECE": "EUR",
        "LU": "EUR", "LUXEMBOURG": "EUR",
        "MT": "EUR", "MALTA": "EUR",
        "CY": "EUR", "CYPRUS": "EUR",
        "EE": "EUR", "ESTONIA": "EUR",
        "LV": "EUR", "LATVIA": "EUR",
        "LT": "EUR", "LITHUANIA": "EUR",
        "SK": "EUR", "SLOVAKIA": "EUR",
        "SI": "EUR", "SLOVENIA": "EUR",
        "HR": "EUR", "CROATIA": "EUR",
        "AD": "EUR", "ANDORRA": "EUR",
        "MC": "EUR", "MONACO": "EUR",
        "SM": "EUR", "SAN MARINO": "EUR",
        "VA": "EUR", "VATICAN CITY": "EUR",
        
        # Europe (Non-Eurozone)
        "GB": "GBP", "UNITED KINGDOM": "GBP", "UK": "GBP",
        "CH": "CHF", "SWITZERLAND": "CHF",
        "SE": "SEK", "SWEDEN": "SEK",
        "NO": "NOK", "NORWAY": "NOK",
        "DK": "DKK", "DENMARK": "DKK",
        "PL": "PLN", "POLAND": "PLN",
        "CZ": "CZK", "CZECH REPUBLIC": "CZK",
        "HU": "HUF", "HUNGARY": "HUF",
        "RO": "RON", "ROMANIA": "RON",
        "BG": "BGN", "BULGARIA": "BGN",
        "IS": "ISK", "ICELAND": "ISK",
        "UA": "UAH", "UKRAINE": "UAH",
        "RU": "RUB", "RUSSIA": "RUB",
        "BY": "BYN", "BELARUS": "BYN",
        "MD": "MDL", "MOLDOVA": "MDL",
        "GE": "GEL", "GEORGIA": "GEL",
        "AM": "AMD", "ARMENIA": "AMD",
        "AZ": "AZN", "AZERBAIJAN": "AZN",
        "KZ": "KZT", "KAZAKHSTAN": "KZT",
        "RS": "RSD", "SERBIA": "RSD",
        "BA": "BAM", "BOSNIA AND HERZEGOVINA": "BAM",
        "ME": "EUR", "MONTENEGRO": "EUR",
        "MK": "MKD", "NORTH MACEDONIA": "MKD",
        "AL": "ALL", "ALBANIA": "ALL",
        "XK": "EUR", "KOSOVO": "EUR",
        "LI": "CHF", "LIECHTENSTEIN": "CHF",
        
        # Asia
        "JP": "JPY", "JAPAN": "JPY",
        "CN": "CNY", "CHINA": "CNY",
        "IN": "INR", "INDIA": "INR",
        "KR": "KRW", "SOUTH KOREA": "KRW", "KOREA": "KRW",
        "KP": "KPW", "NORTH KOREA": "KPW",
        "SG": "SGD", "SINGAPORE": "SGD",
        "HK": "HKD", "HONG KONG": "HKD",
        "MY": "MYR", "MALAYSIA": "MYR",
        "TH": "THB", "THAILAND": "THB",
        "ID": "IDR", "INDONESIA": "IDR",
        "PH": "PHP", "PHILIPPINES": "PHP",
        "VN": "VND", "VIETNAM": "VND",
        "TW": "TWD", "TAIWAN": "TWD",
        "BN": "BND", "BRUNEI": "BND",
        "KH": "KHR", "CAMBODIA": "KHR",
        "LA": "LAK", "LAOS": "LAK",
        "MM": "MMK", "MYANMAR": "MMK",
        "BD": "BDT", "BANGLADESH": "BDT",
        "LK": "LKR", "SRI LANKA": "LKR",
        "NP": "NPR", "NEPAL": "NPR",
        "PK": "PKR", "PAKISTAN": "PKR",
        "AF": "AFN", "AFGHANISTAN": "AFN",
        "MV": "MVR", "MALDIVES": "MVR",
        "BT": "BTN", "BHUTAN": "BTN",
        "MO": "MOP", "MACAU": "MOP",
        
        # Central Asia
        "UZ": "UZS", "UZBEKISTAN": "UZS",
        "KG": "KGS", "KYRGYZSTAN": "KGS",
        "TJ": "TJS", "TAJIKISTAN": "TJS",
        "TM": "TMT", "TURKMENISTAN": "TMT",
        
        # Middle East
        "IL": "ILS", "ISRAEL": "ILS",
        "SA": "SAR", "SAUDI ARABIA": "SAR",
        "AE": "AED", "UNITED ARAB EMIRATES": "AED",
        "QA": "QAR", "QATAR": "QAR",
        "TR": "TRY", "TURKEY": "TRY",
        "IR": "IRR", "IRAN": "IRR",
        "IQ": "IQD", "IRAQ": "IQD",
        "KW": "KWD", "KUWAIT": "KWD",
        "BH": "BHD", "BAHRAIN": "BHD",
        "OM": "OMR", "OMAN": "OMR",
        "JO": "JOD", "JORDAN": "JOD",
        "LB": "LBP", "LEBANON": "LBP",
        "SY": "SYP", "SYRIA": "SYP",
        "YE": "YER", "YEMEN": "YER",
        "PS": "ILS", "PALESTINE": "ILS",
        
        # Oceania
        "AU": "AUD", "AUSTRALIA": "AUD",
        "NZ": "NZD", "NEW ZEALAND": "NZD",
        "PG": "PGK", "PAPUA NEW GUINEA": "PGK",
        "FJ": "FJD", "FIJI": "FJD",
        "SB": "SBD", "SOLOMON ISLANDS": "SBD",
        "VU": "VUV", "VANUATU": "VUV",
        "WS": "WST", "SAMOA": "WST",
        "TO": "TOP", "TONGA": "TOP",
        "NU": "NZD", "NIUE": "NZD",
        "CK": "NZD", "COOK ISLANDS": "NZD",
        
        # South America
        "BR": "BRL", "BRAZIL": "BRL",
        "AR": "ARS", "ARGENTINA": "ARS",
        "CL": "CLP", "CHILE": "CLP",
        "CO": "COP", "COLOMBIA": "COP",
        "PE": "PEN", "PERU": "PEN",
        "VE": "VES", "VENEZUELA": "VES",
        "EC": "USD", "ECUADOR": "USD",
        "BO": "BOB", "BOLIVIA": "BOB",
        "PY": "PYG", "PARAGUAY": "PYG",
        "UY": "UYU", "URUGUAY": "UYU",
        "GY": "GYD", "GUYANA": "GYD",
        "SR": "SRD", "SURINAME": "SRD",
        "GF": "EUR", "FRENCH GUIANA": "EUR",
        
        # Africa
        "ZA": "ZAR", "SOUTH AFRICA": "ZAR",
        "EG": "EGP", "EGYPT": "EGP",
        "NG": "NGN", "NIGERIA": "NGN",
        "KE": "KES", "KENYA": "KES",
        "MA": "MAD", "MOROCCO": "MAD",
        "DZ": "DZD", "ALGERIA": "DZD",
        "TN": "TND", "TUNISIA": "TND",
        "LY": "LYD", "LIBYA": "LYD",
        "GH": "GHS", "GHANA": "GHS",
        "ET": "ETB", "ETHIOPIA": "ETB",
        "TZ": "TZS", "TANZANIA": "TZS",
        "UG": "UGX", "UGANDA": "UGX",
        "RW": "RWF", "RWANDA": "RWF",
        "BW": "BWP", "BOTSWANA": "BWP",
        "ZM": "ZMW", "ZAMBIA": "ZMW",
        "ZW": "ZWL", "ZIMBABWE": "ZWL",
        "MW": "MWK", "MALAWI": "MWK",
        "MZ": "MZN", "MOZAMBIQUE": "MZN",
        "AO": "AOA", "ANGOLA": "AOA",
        "CD": "CDF", "DEMOCRATIC REPUBLIC OF THE CONGO": "CDF",
        "CG": "XAF", "CONGO": "XAF",
        "CI": "XOF", "IVORY COAST": "XOF",
        "SN": "XOF", "SENEGAL": "XOF",
        "ML": "XOF", "MALI": "XOF",
        "BF": "XOF", "BURKINA FASO": "XOF",
        "NE": "XOF", "NIGER": "XOF",
        "TD": "XAF", "CHAD": "XAF",
        "CM": "XAF", "CAMEROON": "XAF",
        "GA": "XAF", "GABON": "XAF",
        "CF": "XAF", "CENTRAL AFRICAN REPUBLIC": "XAF",
        "DJ": "DJF", "DJIBOUTI": "DJF",
        "ER": "ERN", "ERITREA": "ERN",
        "SO": "SOS", "SOMALIA": "SOS",
        "SS": "SSP", "SOUTH SUDAN": "SSP",
        "GM": "GMD", "GAMBIA": "GMD",
        "GN": "GNF", "GUINEA": "GNF",
        "SL": "SLL", "SIERRA LEONE": "SLL",
        "LR": "LRD", "LIBERIA": "LRD",
        "BI": "BIF", "BURUNDI": "BIF",
        "MG": "MGA", "MADAGASCAR": "MGA",
        "MU": "MUR", "MAURITIUS": "MUR",
        "SC": "SCR", "SEYCHELLES": "SCR",
        "KM": "KMF", "COMOROS": "KMF",
        "ST": "STN", "SAO TOME AND PRINCIPE": "STN",
        "CV": "CVE", "CAPE VERDE": "CVE",
        "EH": "MAD", "WESTERN SAHARA": "MAD",
        "NA": "NAD", "NAMIBIA": "NAD",
        "SZ": "SZL", "ESWATINI": "SZL",
        "LS": "LSL", "LESOTHO": "LSL",
        "MR": "MRU", "MAURITANIA": "MRU",
    }
    
    return country_to_currency.get(country, "USD")


class OrderService:
    """
    Comprehensive order service with advanced pricing and security validation
    
    CRITICAL CALCULATION METHODOLOGY:
    ================================
    
    This service is responsible for ALL order total calculations. All calculations
    are performed on the backend (NEVER trust frontend prices) and follow this formula:
    
    SUBTOTAL = SUM(quantity × price_per_unit) for all items
    TOTAL = SUBTOTAL + SHIPPING_COST + TAX_AMOUNT - DISCOUNT_AMOUNT
    
    Calculation Lifecycle:
    
    1. AT ORDER CREATION TIME:
       - User submits checkout request from frontend (may include incorrect prices)
       - _validate_and_recalculate_prices() recalculates all item prices from database
       - _calculate_final_order_total() calculates subtotal = SUM(item.quantity × item.backend_price)
       - Order is created with calculated_subtotal stored in order.subtotal field
       - If any price mismatch between frontend and backend is detected, log it for security audit
    
    2. AT ORDER RETRIEVAL TIME (for admin dashboard):
       - Order is fetched from database with all items
       - AdminService._calculate_subtotal_from_items() recalculates subtotal = SUM(quantity × price_per_unit)
       - This serves as data integrity check and provides audit trail
       - If stored subtotal != calculated subtotal, use calculated value (stored may be corrupted)
    
    Key Rules:
    - NEVER calculate prices on frontend (display only)
    - ALWAYS recalculate on backend before storage
    - Quantity MUST be multiplied by price_per_unit (not frontend's total_price)
    - All calculations use backend prices (sale_price if available, else base_price)
    - Calculations are atomic - all or nothing (transactions)
    - All price discrepancies are logged for security audit
    
    This ensures:
    ✓ Data integrity: Prices always match database source
    ✓ Security: Frontend cannot inject false prices
    ✓ Audit trail: All calculations are traceable to database
    ✓ Accuracy: Quantity always considered in calculations
    """
    
    def __init__(self, db: AsyncSession, lock_service=None):
        self.db = db
        self.inventory_service = InventoryService(db, lock_service)
        self.tax_service = TaxService(db)
        self.shipping_service = ShippingService(db)
        self.discount_engine = DiscountEngine(db)

    async def calc_pricing(
        self,
        cart_items: List[CartItem],
        shipping_address: Address,
        shipping_method_id: UUID,
        discount_code: Optional[str] = None,
        currency: str = "USD"
    ) -> PricingCalculationResult:
        """
        Calculate comprehensive pricing with all components
        This is the authoritative pricing calculation - NEVER trust frontend prices
        """
        logger.info(f"Calculating comprehensive pricing for {len(cart_items)} items")
        
        # Step 1: Calculate subtotal from product variant sale prices
        subtotal = Decimal('0.00')
        item_breakdown = []
        
        for item in cart_items:
            # Get current price from variant (sale_price if available, otherwise base_price)
            variant_price = Decimal(str(item.variant.sale_price or item.variant.base_price))
            item_total = variant_price * Decimal(str(item.quantity))
            subtotal += item_total
            
            item_breakdown.append({
                'variant_id': str(item.variant.id),
                'variant_name': item.variant.name,
                'quantity': item.quantity,
                'unit_price': float(variant_price),
                'total_price': float(item_total),
                'on_sale': item.variant.sale_price is not None,
                'original_price': float(item.variant.base_price) if item.variant.sale_price else None
            })
        
        logger.info(f"Calculated subtotal: ${subtotal}")
        
        # Step 2: Calculate shipping cost
        shipping_cost = Decimal('0.00')
        shipping_method = await self.shipping_service.get(shipping_method_id)
        if shipping_method and shipping_method.is_active:
            shipping_cost = Decimal(str(shipping_method.price))
            logger.info(f"Shipping cost: ${shipping_cost} ({shipping_method.name})")
        
        # Step 3: Calculate tax based on shipping address
        
        tax_rate = await self.tax_service.rate(
            country_code=None, 
            province_code=None, 
            province_name=shipping_address.state,
            country_name=shipping_address.country or "United States"
        )
        # print(shipping_address.country,'====',
        #     shipping_address.state, tax_rate)
        # Tax is calculated on subtotal only (not shipping in most jurisdictions)
        tax_amount = (subtotal * Decimal(str(tax_rate))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        logger.info(f"Tax calculation", metadata={
    "tax_rate_percent": tax_rate * 100,
    "subtotal": float(subtotal),
    "tax_amount": float(tax_amount)
})
        
        # Step 4: Apply discount if provided
        discount_amount = Decimal('0.00')
        discount_info = None
        if discount_code:
            try:
                validation_result = await self.discount_engine.validate_discount_code(
                    discount_code,
                    subtotal=float(subtotal)
                )
                if validation_result["is_valid"]:
                    discount = validation_result["discount"]
                    if discount.type == DiscountType.PERCENTAGE.value:
                        discount_amount = (subtotal * Decimal(str(discount.value / 100))).quantize(
                            Decimal('0.01'), rounding=ROUND_HALF_UP
                        )
                        if discount.maximum_discount:
                            discount_amount = min(discount_amount, Decimal(str(discount.maximum_discount)))
                    elif discount.type == DiscountType.FIXED_AMOUNT.value:
                        discount_amount = min(Decimal(str(discount.value)), subtotal)
                    elif discount.type == DiscountType.FREE_SHIPPING.value:
                        discount_amount = shipping_cost
                        shipping_cost = Decimal('0.00')
                    
                    discount_info = {
                        'code': discount.code,
                        'type': discount.type,
                        'value': discount.value,
                        'amount': float(discount_amount)
                    }
                    logger.info(f"Applied discount {discount_code}: -${discount_amount}")
            except Exception as e:
                logger.warning(f"Failed to apply discount {discount_code}: {e}")
        
        # Step 5: Calculate final total
        total_amount = (subtotal + shipping_cost + tax_amount - discount_amount).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        
        # Ensure total is never negative
        if total_amount < Decimal('0.00'):
            total_amount = Decimal('0.00')
        
        logger.info(f"Final total: ${total_amount}")
        
        # Create detailed breakdown
        breakdown = {
            'items': item_breakdown,
            'subtotal': float(subtotal),
            'shipping': {
                'method_id': str(shipping_method_id),
                'method_name': shipping_method.name if shipping_method else None,
                'cost': float(shipping_cost)
            },
            'tax': {
                'rate': tax_rate,
                'amount': float(tax_amount),
                'location': f"{shipping_address.country}-{shipping_address.state}"
            },
            'discount': discount_info,
            'total': float(total_amount),
            'currency': currency,
            'calculated_at': datetime.utcnow().isoformat()
        }
        
        return PricingCalculationResult(
            subtotal=subtotal,
            shipping_cost=shipping_cost,
            tax_amount=tax_amount,
            tax_rate=float(tax_rate),
            discount_amount=discount_amount,
            total_amount=total_amount,
            currency=currency,
            breakdown=breakdown
        )

    async def validate_checkout(
        self,
        user_id: UUID,
        request: CheckoutRequest
    ) -> Dict[str, Any]:
        """
        Comprehensive checkout validation with detailed error reporting
        """
        def _clean_result(r: dict) -> dict:
            """Ensure result is fully JSON-serializable."""
            return {
                'valid': bool(r.get('valid', False)),
                'can_proceed': bool(r.get('can_proceed', False)),
                'errors': [
                    e if isinstance(e, dict) else {'message': str(e)}
                    for e in r.get('errors', [])
                ],
                'warnings': r.get('warnings', []),
                'pricing': r.get('pricing'),
            }

        validation_result = {
            'valid': True,
            'can_proceed': True,
            'errors': [],
            'warnings': [],
            'pricing': None
        }
        
        try:
            # Step 1: Validate cart exists and has items
            cart_service = CartService(self.db)
            cart_validation = await cart_service.validate_cart(user_id)
            
            logger.info(f"Cart validation result: valid={cart_validation.get('valid')}, can_checkout={cart_validation.get('can_checkout')}")
            if cart_validation.get('issues'):
                for issue in cart_validation.get('issues'):
                    logger.info(f"Cart issue: {issue}")
            
            if not cart_validation.get('valid', False):
                validation_result['valid'] = False
                validation_result['can_proceed'] = False
                validation_result['errors'].extend(cart_validation.get('issues', []))
                return _clean_result(validation_result)
            
            cart = cart_validation['cart']
            
            # Verify cart has items before proceeding
            if not cart or not hasattr(cart, 'items') or not cart.items:
                validation_result['valid'] = False
                validation_result['can_proceed'] = False
                validation_result['errors'].append({
                    'type': 'cart_validation',
                    'severity': 'error', 
                    'message': 'Cart has no valid items for checkout'
                })
                return _clean_result(validation_result)
            
            # Step 2: Validate shipping address
            shipping_address_result = await self.db.execute(
                select(Address).where(
                    and_(Address.id == request.shipping_address_id, Address.user_id == user_id)
                )
            )
            shipping_address = shipping_address_result.scalar_one_or_none()
            
            if not shipping_address:
                validation_result['valid'] = False
                validation_result['can_proceed'] = False
                validation_result['errors'].append({
                    'field': 'shipping_address_id',
                    'message': 'Invalid shipping address'
                })
                return _clean_result(validation_result)
            
            # Step 3: Validate shipping method
            shipping_method = await self.shipping_service.get(request.shipping_method_id)
            if not shipping_method or not shipping_method.is_active:
                validation_result['valid'] = False
                validation_result['can_proceed'] = False
                validation_result['errors'].append({
                    'field': 'shipping_method_id',
                    'message': 'Invalid or inactive shipping method'
                })
                return _clean_result(validation_result)
            
            # Step 4: Validate payment method
            payment_method_result = await self.db.execute(
                select(PaymentMethod).where(
                    and_(PaymentMethod.id == request.payment_method_id, PaymentMethod.user_id == user_id)
                )
            )
            payment_method = payment_method_result.scalar_one_or_none()
            
            if not payment_method:
                validation_result['valid'] = False
                validation_result['can_proceed'] = False
                validation_result['errors'].append({
                    'field': 'payment_method_id',
                    'message': 'Invalid payment method'
                })
                return _clean_result(validation_result)
            
            # Step 5: Calculate comprehensive pricing
            pricing = await self.calc_pricing(
                cart.items,
                shipping_address,
                request.shipping_method_id,
                getattr(request, 'discount_code', None),
                getattr(request, 'currency', 'USD')
            )
            validation_result['pricing'] = pricing['breakdown']
            
            # Step 6: Validate frontend price if provided
            if hasattr(request, 'frontend_calculated_total') and request.frontend_calculated_total:
                frontend_total = Decimal(str(request.frontend_calculated_total))
                backend_total = pricing['total_amount']
                price_difference = abs(frontend_total - backend_total)
                
                # Allow small rounding differences (up to 1 cent)
                if price_difference > Decimal('0.01'):
                    validation_result['warnings'].append({
                        'type': 'price_mismatch',
                        'message': f'Price mismatch detected. Frontend: ${frontend_total}, Backend: ${backend_total}',
                        'frontend_total': float(frontend_total),
                        'backend_total': float(backend_total),
                        'difference': float(price_difference)
                    })
            
            logger.info(f"Checkout validation completed for user {user_id}: {validation_result['valid']}")
            return _clean_result(validation_result)
            
        except Exception as e:
            import traceback
            logger.error(f"Checkout validation failed for user {user_id}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            validation_result['valid'] = False
            validation_result['can_proceed'] = False
            validation_result['errors'].append({
                'type': 'system_error',
                'message': f'Checkout validation failed: {str(e)}'
            })
            return _clean_result(validation_result)

    async def create(
        self,
        user_id: UUID,
        request: CheckoutRequest,
        background_tasks: BackgroundTasks,
        idempotency_key: Optional[str] = None
    ) -> OrderResponse:
        """
        Create (place) an order with comprehensive validation and security checks.
        This is the single order-creation path - both POST /orders/ and
        POST /orders/checkout/ call this method.
        """
        logger.info(f"Processing order for user {user_id}")
        
        # Step 1: Comprehensive validation
        validation_result = await self.validate_checkout(user_id, request)
        
        if not validation_result['can_proceed']:
            error_messages = [error['message'] for error in validation_result['errors']]
            raise HTTPException(
                status_code=400,
                detail={
                    'message': 'Checkout validation failed',
                    'errors': validation_result['errors'],
                    'warnings': validation_result['warnings']
                }
            )
        
        # Step 2: Get cart from database to access items for order creation
        # We need to fetch the cart fresh from the database in case items were updated
        cart_result = await self.db.execute(
            select(Cart).where(Cart.user_id == user_id).options(
                selectinload(Cart.items).selectinload(CartItem.variant)
            )
        )
        cart = cart_result.scalar_one_or_none()
        
        # Validate cart still has items (defensive check)
        if not cart:
            raise HTTPException(
                status_code=400,
                detail="Cart not found"
            )
        
        if not cart.items:
            raise HTTPException(
                status_code=400,
                detail="Cart is empty - no items to checkout"
            )
        
        pricing = validation_result['pricing']
        
        # Step 2: Get addresses and shipping method
        shipping_address_result = await self.db.execute(
            select(Address).where(Address.id == request.shipping_address_id)
        )
        shipping_address = shipping_address_result.scalar_one()
        
        shipping_method_result = await self.db.execute(
            select(ShippingMethod).where(ShippingMethod.id == request.shipping_method_id)
        )
        shipping_method = shipping_method_result.scalar_one()
        
        
        try:
            # Step 3: PROCESS PAYMENT FIRST (before creating order)
            # Generate a temp order id and deterministic order number using it
            temp_order_id = uuid7()  # Temporary ID for payment processing
            order_number = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{temp_order_id.hex[:12].upper()}"
            
            temp_currency = get_currency_from_address(shipping_address.country) if shipping_address.country else "USD"
            
            placeholder_order = Order(
                id=temp_order_id,
                order_number=order_number,
                user_id=user_id,
                order_status="pending",
                payment_status="pending",
                fulfillment_status="unfulfilled",
                subtotal=Decimal('0.00'),
                shipping_cost=Decimal('0.00'),
                tax_amount=Decimal('0.00'),
                total_amount=Decimal('0.00'),
                currency=temp_currency
            )
            # Provide minimal address dicts to satisfy NOT NULL constraints
            placeholder_order.billing_address = {}
            placeholder_order.shipping_address = {}
            self.db.add(placeholder_order)
            await self.db.flush()

            # Process payment with Stripe using backend-calculated total
            payment_service = PaymentService(self.db)
            payment_idempotency_key = (
                f"payment_{temp_order_id}_{idempotency_key}" if idempotency_key else f"payment_{temp_order_id}"
            )

            logger.info(f"Processing payment for order {order_number}, amount: {pricing['total']}")
            
            payment_result = await payment_service.process_idempotent(
                user_id=user_id,
                order_id=temp_order_id,  # Use temp ID since order doesn't exist yet
                amount=pricing['total'],
                payment_method_id=request.payment_method_id,
                idempotency_key=payment_idempotency_key,
                request_id=str(uuid7()),
                frontend_calculated_amount=getattr(request, "frontend_calculated_total", None)
            )

            # Check payment status - MUST be successful before creating order
            if payment_result.get("status") != "succeeded":
                error_message = payment_result.get("error", "Payment processing failed")
                logger.error(f"Payment failed for order {order_number}: {error_message}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Payment failed: {error_message}"
                )
            
            logger.info(f"Payment successful for order {order_number}, updating placeholder order...")
            # Update placeholder order with final details
            order = await self.db.get(Order, temp_order_id)
            order.order_status = "confirmed"
            order.payment_status = "paid"
            order.fulfillment_status = "unfulfilled"
            order.subtotal = pricing['subtotal']
            order.shipping_cost = pricing['shipping']['cost']
            order.tax_amount = pricing['tax']['amount']
            order.tax_rate = pricing['tax']['rate']
            order.total_amount = pricing['total']
            order.currency = pricing['currency']
            order.shipping_method = shipping_method.name
            order.billing_address = {
                'street': shipping_address.street,
                'city': shipping_address.city,
                'state': shipping_address.state,
                'country': shipping_address.country,
                'post_code': shipping_address.post_code
            }
            order.shipping_address = order.billing_address.copy()
            order.customer_notes = request.notes
            await self.db.flush()
            
            # Step 5: Create order items and update inventory
            order_items_list = []
            for cart_item in cart.items:
                variant_price = cart_item.variant.sale_price or cart_item.variant.base_price
                
                order_item = OrderItem(
                    id=uuid7(),
                    order_id=order.id,
                    variant_id=cart_item.variant_id,
                    quantity=cart_item.quantity,
                    price_per_unit=variant_price,
                    total_price=variant_price * cart_item.quantity
                )
                self.db.add(order_item)
                order_items_list.append(order_item)
                
                # Update inventory
                adjustment = StockAdjustmentCreate(
                    variant_id=cart_item.variant_id,
                    quantity_change=-cart_item.quantity,
                    reason=f"Order placed: {order_number}",
                    notes=f"Auto-adjusted inventory for order {order_number}"
                )
                await self.inventory_service.adjust_stock(
                    adjustment,
                    adjusted_by_user_id=user_id,
                    commit=False
                )

            # Send invoice/confirmation email in background
            try:
                user_result = await self.db.execute(select(User).where(User.id == user_id))
                user = user_result.scalar_one_or_none()
                if user and getattr(user, "email", None):
                    email_items = [
                        {
                            "name": cart_item.variant.name if cart_item.variant else "Item",
                            "quantity": cart_item.quantity,
                            "price": float(cart_item.variant.sale_price or cart_item.variant.base_price or 0)
                        }
                        for cart_item in cart.items
                    ]
                    email_service = EmailService(self.db)
                    background_tasks.add_task(
                        email_service.send_order_confirmation_email,
                        recipient_email=user.email,
                        customer_name=getattr(user, "full_name", "Customer"),
                        order_number=order.order_number,
                        order_date=order.created_at or datetime.utcnow(),
                        total_amount=order.total_amount,
                        items=email_items,
                        shipping_address=order.shipping_address
                    )
            except Exception as email_error:
                logger.error(f"Failed to schedule invoice email: {email_error}")
            
            # Clear cart
            await self.db.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
            
            # Explicitly commit the transaction to persist all changes
            await self.db.commit()
            
            logger.info("Order completed", metadata={
                "order_id": str(order.id),
                "order_number": order_number,
                "user_id": str(user_id),
                "total_amount": float(order.total_amount),
                "items_count": len(order_items_list),
                "payment_status": "completed",
                "milestone": "revenue"
            })
            
            # Return order response using the items we collected
            return OrderResponse(
                id=order.id,
                order_number=order.order_number,
                user_id=user_id,
                order_status=order.order_status,
                payment_status=order.payment_status,
                fulfillment_status=order.fulfillment_status,
                total_amount=float(order.total_amount),
                subtotal=float(order.subtotal or 0),
                tax_amount=float(order.tax_amount or 0),
                shipping_cost=float(order.shipping_cost or 0),
                discount_amount=float(getattr(order, 'discount_amount', 0) or 0),
                currency=order.currency,
                tracking_number=getattr(order, 'tracking_number', None),
                estimated_delivery=None,
                shipping_address=order.shipping_address,
                billing_address=order.billing_address,
                items=[
                    OrderItemResponse(
                        id=item.id,
                        variant_id=item.variant_id,
                        quantity=item.quantity,
                        price_per_unit=float(item.price_per_unit),
                        total_price=float(item.total_price),
                        variant=None
                    ) for item in order_items_list
                ],
                created_at=datetime.utcnow(),
                updated_at=None
            )
            
        except HTTPException:
            # Preserve intentional status codes raised above (e.g. 400 on a
            # declined payment) instead of masking them as a 500 below.
            raise
        except Exception as e:
            import traceback
            logger.exception(f"Order creation failed for user {user_id}: {e}\nTraceback: {traceback.format_exc()}")
            # Session will auto-rollback on exception due to the context manager
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Order creation failed due to system error",
                    "traceback": traceback.format_exc()
                }
            )

    async def list(
        self,
        user_id: Optional[UUID] = None,
        page: int = 1,
        limit: int = 10,
        status: Optional[str] = None,
        search: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        q: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get paginated list of orders. If user_id is None, returns all orders (admin)."""
        from sqlalchemy import func
        import traceback

        try:
            offset = (page - 1) * limit

            # Build base query
            base_query = select(Order).options(
                selectinload(Order.items).selectinload(OrderItem.variant).selectinload(ProductVariant.images),
                selectinload(Order.items).selectinload(OrderItem.variant).selectinload(ProductVariant.product),
                selectinload(Order.user)
            )
            count_query = select(func.count()).select_from(Order)

            # Apply filters
            conditions = []

            if user_id:
                conditions.append(Order.user_id == user_id)

            if status:
                conditions.append(Order.order_status == status)

            if q:
                conditions.append(
                    or_(
                        Order.id.cast(String).ilike(f"%{q}%"),
                        Order.user.has(User.email.ilike(f"%{q}%"))
                    )
                )

            if search:
                conditions.append(
                    or_(
                        Order.id.cast(String).ilike(f"%{search}%"),
                        Order.order_number.ilike(f"%{search}%") if hasattr(Order, 'order_number') else text('FALSE')
                    )
                )

            if date_from:
                try:
                    from_date = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                    conditions.append(Order.created_at >= from_date)
                except ValueError:
                    pass

            if date_to:
                try:
                    to_date = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                    conditions.append(Order.created_at <= to_date)
                except ValueError:
                    pass

            if min_price is not None:
                conditions.append(Order.total_amount >= min_price)

            if max_price is not None:
                conditions.append(Order.total_amount <= max_price)

            # Apply all conditions
            if conditions:
                base_query = base_query.where(and_(*conditions))
                count_query = count_query.where(and_(*conditions))

            # Apply sorting
            sort_column = Order.created_at
            if sort_by == "total":
                sort_column = Order.total_amount
            elif sort_by == "status":
                sort_column = Order.order_status

            if sort_order == "asc":
                base_query = base_query.order_by(sort_column.asc())
            else:
                base_query = base_query.order_by(sort_column.desc())

            # Get total count
            total = await self.db.scalar(count_query) or 0

            # Get paginated results
            result = await self.db.execute(base_query.offset(offset).limit(limit))
            orders = result.scalars().all()

            formatted_orders = []
            for order in orders:
                order_response = await self._format_order_response(order)
                order_dict = order_response.model_dump() if hasattr(order_response, 'model_dump') else order_response.dict()
                if order.user:
                    order_dict["customer"] = {
                        "id": str(order.user.id),
                        "email": order.user.email,
                        "name": f"{order.user.firstname} {order.user.lastname}"
                    }
                formatted_orders.append(order_dict)

            return {
                "orders": formatted_orders,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit if limit > 0 else 1
                }
            }
        except Exception as e:
            logger.error(f"Error in list method: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    async def get(self, order_id: UUID, user_id: Optional[UUID] = None) -> Optional[OrderResponse]:
        """Get a specific order by ID. If user_id is provided, only return that user's order."""
        import traceback
        try:
            # Build query - filter by user_id if provided (for regular users), no filter for admins
            if user_id:
                query = select(Order).where(and_(Order.id == order_id, Order.user_id == user_id)).options(
                    selectinload(Order.items).selectinload(OrderItem.variant).selectinload(ProductVariant.images),
                    selectinload(Order.items).selectinload(OrderItem.variant).selectinload(ProductVariant.product),
                    selectinload(Order.user)
                )
            else:
                query = select(Order).where(Order.id == order_id).options(
                    selectinload(Order.items).selectinload(OrderItem.variant).selectinload(ProductVariant.images),
                    selectinload(Order.items).selectinload(OrderItem.variant).selectinload(ProductVariant.product),
                    selectinload(Order.user)
                )

            result = await self.db.execute(query)
            order = result.scalar_one_or_none()

            if not order:
                return None

            return await self._format_order_response(order)
        except Exception as e:
            logger.error(f"Error in get method for order {order_id}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    async def cancel(self, order_id: UUID, user_id: UUID) -> OrderResponse:
        """Cancel an order with transaction safety"""
        query = select(Order).where(and_(Order.id == order_id, Order.user_id == user_id)).with_for_update()
        result = await self.db.execute(query)
        order = result.scalar_one_or_none()

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        if order.order_status not in [OrderStatus.PENDING, OrderStatus.CONFIRMED]:
            raise HTTPException(status_code=400, detail="Order cannot be cancelled")

        # self.db already has an auto-begun transaction from the SELECT above - an
        # explicit self.db.begin() here raises "A transaction is already begun".
        try:
            now = datetime.now(tz=timezone.utc)
            order.order_status = OrderStatus.CANCELLED
            order.fulfillment_status = FulfillmentStatus.CANCELLED
            order.cancelled_at = now

            # Increment stock for cancelled order items
            query_items = select(OrderItem).where(OrderItem.order_id == order.id).options(
                selectinload(OrderItem.variant).selectinload(ProductVariant.inventory)
            )
            order_items_with_inventory = (await self.db.execute(query_items)).scalars().all()

            for item in order_items_with_inventory:
                if not item.variant or not item.variant.inventory:
                    logger.warning(f"No inventory found for variant {item.variant_id} during order cancellation.")
                    continue

                # Use new increment stock method for cancellations
                await self.inventory_service.increment(
                    variant_id=item.variant.id,
                    quantity=item.quantity,
                    location_id=item.variant.inventory.location_id,
                    order_id=order.id,
                    user_id=user_id
                )

            # Add tracking event
            tracking_event = TrackingEvent(
                order_id=order.id,
                status="cancelled",
                description="Order cancelled by customer",
                location="System"
            )
            self.db.add(tracking_event)

            await self.db.commit()
            await self.db.refresh(order)

        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Order cancellation failed: {str(e)}")

        return await self._format_order_response(order)

    async def update_status(
        self, 
        order_id: UUID, 
        status: str, 
        tracking_number: Optional[str] = None,
        carrier_name: Optional[str] = None,
        location: Optional[str] = None,
        description: Optional[str] = None,
        background_tasks = None
    ) -> Order:
        """Update order status (admin function)"""
        query = select(Order).where(Order.id == order_id)
        result = await self.db.execute(query)
        order = result.scalar_one_or_none()

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Convert string status to OrderStatus enum (enum values are lowercase)
        try:
            status_enum = OrderStatus(status.lower())
            order.order_status = status_enum
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid order status: {status}")

        # Set lifecycle timestamps
        now = datetime.now(tz=timezone.utc)
        if status_enum == OrderStatus.CONFIRMED and not order.confirmed_at:
            order.confirmed_at = now
        elif status_enum == OrderStatus.SHIPPED:
            order.shipped_at = now
            if not order.confirmed_at:
                order.confirmed_at = now
        elif status_enum == OrderStatus.DELIVERED:
            order.delivered_at = now
            if not order.shipped_at:
                order.shipped_at = now
            if not order.confirmed_at:
                order.confirmed_at = now
        elif status_enum == OrderStatus.CANCELLED:
            order.cancelled_at = now

        # Auto-update fulfillment_status
        fulfillment_map = {
            OrderStatus.PENDING: FulfillmentStatus.UNFULFILLED,
            OrderStatus.CONFIRMED: FulfillmentStatus.UNFULFILLED,
            OrderStatus.PROCESSING: FulfillmentStatus.UNFULFILLED,
            OrderStatus.SHIPPED: FulfillmentStatus.PARTIAL,
            OrderStatus.DELIVERED: FulfillmentStatus.FULFILLED,
            OrderStatus.CANCELLED: FulfillmentStatus.CANCELLED,
            OrderStatus.REFUNDED: FulfillmentStatus.CANCELLED,
        }
        order.fulfillment_status = fulfillment_map.get(status_enum, order.fulfillment_status)

        if tracking_number:
            order.tracking_number = tracking_number

        # Auto-populate carrier from ShippingMethod if not provided
        if not carrier_name and order.shipping_method:
            from models.commerce.shipping import ShippingMethod
            shipping_method_result = await self.db.execute(
                select(ShippingMethod).where(ShippingMethod.name == order.shipping_method)
            )
            # name isn't unique - several methods can share one (e.g. admin-recreated
            # "Standard"), so take the first match instead of scalar_one_or_none().
            shipping_method = shipping_method_result.scalars().first()
            if shipping_method and shipping_method.carrier:
                carrier_name = shipping_method.carrier

        if carrier_name:
            order.carrier = carrier_name

        # Generate appropriate description based on status
        if not description:
            status_descriptions = {
                'pending': 'Order placed and awaiting confirmation',
                'confirmed': 'Order confirmed and payment processed',
                'processing': 'Order is being prepared for shipment',
                'shipped': 'Package has been shipped and is in transit',
                'out_for_delivery': 'Package is out for delivery',
                'delivered': 'Package has been successfully delivered',
                'cancelled': 'Order has been cancelled'
            }
            description = status_descriptions.get(status, f"Order status updated to {status}")

        # Determine location based on status if not provided
        if not location:
            location_map = {
                'pending': 'System',
                'confirmed': 'Processing Center',
                'processing': 'Warehouse',
                'shipped': 'In Transit',
                'out_for_delivery': 'Local Distribution Center',
                'delivered': 'Delivery Address',
                'cancelled': 'System'
            }
            location = location_map.get(status, 'Fulfillment Center')

        # Add tracking event
        tracking_event = TrackingEvent(
            order_id=order.id,
            status=status,
            description=description,
            location=location
        )
        self.db.add(tracking_event)

        await self.db.commit()
        await self.db.refresh(order)
        
        # Send shipping update email for shipped/delivered orders
        if status in ['shipped', 'delivered'] and background_tasks:
            # Get user details for email
            user_result = await self.db.execute(
                select(User).where(User.id == order.user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if user and user.email:
                email_service = EmailService(self.db)
                if status == 'shipped':
                    # Send shipping update email
                    email_service.send_shipping_update(
                        background_tasks=background_tasks,
                        to_email=user.email,
                        customer_name=user.firstname or "Customer",
                        order_number=order.order_number or str(order.id)[:8],
                        tracking_number=order.tracking_number or "N/A",
                        carrier=order.carrier or "N/A",
                        estimated_delivery=order.delivered_at or datetime.utcnow() + timedelta(days=3),
                        tracking_url=None
                    )
                elif status == 'delivered':
                    # Send order delivered email
                    # Format shipping address
                    shipping_addr = order.shipping_address or {}
                    if isinstance(shipping_addr, dict):
                        address_str = f"{shipping_addr.get('street', '')}, {shipping_addr.get('city', '')}, {shipping_addr.get('state', '')} {shipping_addr.get('post_code', '')}"
                    else:
                        address_str = "Your delivery address"
                    
                    email_service.send_order_delivered(
                        background_tasks=background_tasks,
                        to_email=user.email,
                        customer_name=user.firstname or "Customer",
                        order_id=str(order.id),
                        order_number=order.order_number or str(order.id)[:8],
                        tracking_number=order.tracking_number or "N/A",
                        delivery_date=order.delivered_at or datetime.utcnow(),
                        delivery_address=address_str,
                        delivery_notes=None
                    )
        
        return order

    async def _format_order_response(self, order: Order) -> OrderResponse:
        """Format order for response"""
        items = []
        calculated_subtotal = 0
        
        for item in order.items:
            # Include variant details with images
            variant_data = None
            if item.variant:
                variant_data = {
                    "id": str(item.variant.id),
                    "name": item.variant.name,
                    "product_name": item.variant.product.name if item.variant.product else None,
                    "product_id": str(item.variant.product_id) if item.variant.product_id else None,
                    "sku": item.variant.sku,
                    "images": [
                        {
                            "id": str(img.id),
                            "url": img.url,
                            "is_primary": img.is_primary,
                            "sort_order": img.sort_order
                        }
                        for img in item.variant.images
                    ] if item.variant.images else []
                }
            else:
                logger.warning(f"Order item {item.id} has no variant associated")
            
            # Add to calculated subtotal
            calculated_subtotal += item.total_price or 0
            
            items.append(OrderItemResponse(
                id=item.id,
                variant_id=item.variant.id if item.variant else item.variant_id,
                quantity=item.quantity,
                price_per_unit=float(item.price_per_unit) if item.price_per_unit else 0.0,
                total_price=float(item.total_price) if item.total_price else 0.0,
                variant=variant_data
            ))

        # Use calculated subtotal if order subtotal is missing or zero
        display_subtotal = order.subtotal if order.subtotal and order.subtotal > 0 else calculated_subtotal

        # CRITICAL FIX: Validate and correct order total before returning to frontend
        expected_total = display_subtotal + (order.shipping_cost or 0) + (order.tax_amount or 0) - (order.discount_amount or 0)
        
        # If the stored total is wrong, log it and use the calculated total
        if abs(expected_total - order.total_amount) > 0.01:
            logger.warning(f"🔧 ORDER TOTAL CORRECTION for order {order.id}:")
            logger.warning(f"   Stored total:    ${order.total_amount:.2f}")
            logger.warning(f"   Calculated total: ${expected_total:.2f}")
            logger.warning(f"   Subtotal:        ${display_subtotal:.2f}")
            logger.warning(f"   Shipping:        ${order.shipping_cost or 0:.2f}")
            logger.warning(f"   Tax:             ${order.tax_amount or 0:.2f}")
            logger.warning(f"   Discount:        ${order.discount_amount or 0:.2f}")
            
            # Use the calculated total instead of the stored (incorrect) total
            corrected_total = expected_total
            
            # Optionally update the database with the correct total
            try:
                order.total_amount = corrected_total
                await self.db.commit()
                # updated_at is DB-computed (onupdate=func.now()), so it's always
                # marked stale after this UPDATE regardless of expire_on_commit -
                # refresh now, before the plain attribute reads below.
                await self.db.refresh(order)
                logger.info(f"✅ Updated order {order.id} total in database to ${corrected_total:.2f}")
            except Exception as e:
                logger.error(f"Failed to update order total in database: {e}")
                # Continue with the corrected total even if DB update fails
        else:
            corrected_total = order.total_amount

        # Calculate estimated delivery
        estimated_delivery = None
        current_status = (order.order_status.value if hasattr(order.order_status, 'value') else str(order.order_status or '')).lower()
        if current_status in ["confirmed", "shipped"]:
            estimated_days = 5  # Default, could be from shipping method
            estimated_delivery = (order.created_at + timedelta(days=estimated_days)).isoformat()

        # Generate tracking URL if tracking number and shipping method exist
        tracking_url = None
        if order.tracking_number and order.shipping_method:
            from models.commerce.shipping import ShippingMethod
            shipping_method_result = await self.db.execute(
                select(ShippingMethod).where(ShippingMethod.name == order.shipping_method)
            )
            # name isn't unique - take the first match instead of scalar_one_or_none().
            shipping_method = shipping_method_result.scalars().first()
            if shipping_method and shipping_method.tracking_url_template:
                tracking_url = shipping_method.tracking_url_template.replace('{tracking_number}', order.tracking_number)

        return OrderResponse(
            id=order.id,
            order_number=order.order_number,
            user_id=order.user_id,
            order_status=order.order_status,
            payment_status=order.payment_status,
            fulfillment_status=order.fulfillment_status,
            total_amount=float(corrected_total),  # Use corrected total instead of order.total_amount
            subtotal=float(display_subtotal) if display_subtotal else None,
            tax_amount=float(order.tax_amount) if order.tax_amount else None,
            shipping_cost=float(order.shipping_cost) if order.shipping_cost else None,
            discount_amount=float(order.discount_amount) if order.discount_amount else None,
            currency=order.currency,  # Use order's currency
            shipping_method=order.shipping_method,
            tracking_number=order.tracking_number,
            carrier=order.carrier,
            tracking_url=tracking_url,
            estimated_delivery=estimated_delivery,
            shipping_address=order.shipping_address,
            billing_address=order.billing_address,
            customer_notes=order.customer_notes,
            internal_notes=order.internal_notes,
            items=items,
            created_at=order.created_at if order.created_at else datetime.utcnow(),
            updated_at=order.updated_at
        )

    async def _validate_and_recalculate_prices(self, cart) -> Dict[str, Any]:
        """
        CRITICAL SECURITY: Validate all prices against current database prices
        Never trust frontend prices - always recalculate on backend
        """
        try:
            validated_items = []
            total_discrepancies = []
            price_updates = []  # Track items with price changes for frontend notification
            
            active_cart_items = [item for item in cart.items if not getattr(item, 'saved_for_later', False)]
            
            for cart_item in active_cart_items:
                # Fetch current variant details from database
                variant_result = await self.db.execute(
                    select(ProductVariant).where(ProductVariant.id == cart_item.variant.id).options(
                        selectinload(ProductVariant.product)
                    )
                )
                variant = variant_result.scalar_one_or_none()
                
                if not variant:
                    return {
                        "valid": False,
                        "message": f"Product variant {cart_item.variant.id} no longer exists"
                    }
                
                # Get current backend price (sale_price takes precedence over base_price)
                backend_price = variant.sale_price if variant.sale_price else variant.base_price
                backend_total = backend_price * cart_item.quantity
                
                # Compare with cart price (allow small floating point differences)
                price_difference = abs(backend_price - cart_item.price_per_unit)
                total_difference = abs(backend_total - cart_item.total_price)
                
                if price_difference > 0.01 or total_difference > 0.01:
                    discrepancy_info = {
                        "variant_id": str(cart_item.variant.id),
                        "product_name": variant.product.name if variant.product else "Unknown",
                        "variant_name": variant.name,
                        "cart_price": cart_item.price_per_unit,
                        "backend_price": backend_price,
                        "difference": price_difference
                    }
                    total_discrepancies.append(discrepancy_info)
                    
                    # Add to price updates for frontend notification
                    price_updates.append({
                        "variant_id": str(cart_item.variant.id),
                        "product_name": variant.product.name if variant.product else "Unknown",
                        "variant_name": variant.name,
                        "old_price": cart_item.price_per_unit,
                        "new_price": backend_price,
                        "quantity": cart_item.quantity,
                        "old_total": cart_item.total_price,
                        "new_total": backend_total,
                        "is_sale": variant.sale_price is not None,
                        "price_increased": backend_price > cart_item.price_per_unit
                    })
                
                # Always use backend-calculated prices
                validated_items.append({
                    "variant_id": cart_item.variant.id,
                    "quantity": cart_item.quantity,
                    "cart_price": cart_item.price_per_unit,
                    "backend_price": backend_price,
                    "backend_total": backend_total,
                    "product_name": variant.product.name if variant.product else "Unknown",
                    "variant_name": variant.name
                })
            
            # Calculate backend subtotal
            backend_subtotal = sum(item["backend_total"] for item in validated_items)
            
            # If there are price discrepancies, we can either:
            # 1. Reject the order (strict security)
            # 2. Accept with backend prices (user-friendly)
            # For security, we'll log discrepancies but use backend prices
            
            if total_discrepancies:
                logger.warning(
                    "Price discrepancies detected during checkout",
                    metadata={
                        "discrepancies": total_discrepancies,
                        "total_items": len(validated_items)
                    }
                )
            
            return {
                "valid": True,
                "validated_items": validated_items,
                "backend_subtotal": backend_subtotal,
                "total_amount": backend_subtotal,  # Will be updated with shipping/tax
                "price_discrepancies": total_discrepancies,
                "price_updates": price_updates  # For frontend notification
            }
            
        except Exception as e:
            return {
                "valid": False,
                "message": f"Price validation failed: {str(e)}"
            }

    async def _calculate_final_order_total(
        self,
        validated_items: List[Dict],
        shipping_method,
        shipping_address,
        promocode=None
    ) -> Dict[str, float]:
        """
        Calculate final order total with shipping, taxes, and discounts
        All calculations done on backend - never trust frontend
        """
        try:
            # Calculate subtotal from validated backend prices
            subtotal = sum(item["backend_total"] for item in validated_items)
            
            # Calculate shipping cost using simplified logic
            shipping_cost = 0.0
            if shipping_method:
                # Use ShippingService for proper calculation
                from services.commerce.shipping import ShippingService
                shipping_service = ShippingService(self.db)
                
                # Extract address info for shipping calculation
                address_dict = {
                    'country': shipping_address.get('country', 'US'),
                    'state': shipping_address.get('state'),
                    'city': shipping_address.get('city'),
                    'postal_code': shipping_address.get('postal_code')
                }
                
                shipping_cost = await shipping_service.calc_cost(
                    cart_subtotal=subtotal,
                    address=address_dict,
                    shipping_method_id=shipping_method.id if hasattr(shipping_method, 'id') else None
                )
            
            # Calculate tax based on shipping address (tax applies to subtotal + shipping)
            tax_rate = await self._get_tax_rate(shipping_address)
            taxable_amount = subtotal + shipping_cost  # Tax applies to subtotal + shipping
            tax_amount = taxable_amount * tax_rate
            
            # Apply any discounts (from promocodes, etc.)
            discount_amount = self._calculate_discount_amount(subtotal, promocode)
            
            # Calculate final total
            total_amount = subtotal + shipping_cost + tax_amount - discount_amount
            
            return {
                "subtotal": subtotal,
                "shipping_cost": shipping_cost,
                "tax_amount": tax_amount,
                "tax_rate": tax_rate,
                "discount_amount": discount_amount,
                "total_amount": total_amount
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to calculate order total: {str(e)}")

    def _calculate_discount_amount(self, subtotal: float, promocode=None) -> float:
        """Calculate discount amount from the cart's applied promocode, if any and still active."""
        if not promocode or not promocode.is_active:
            return 0.0

        if promocode.discount_type == "percentage":
            discount = (subtotal * float(promocode.value)) / 100
        else:
            discount = float(promocode.value)

        if promocode.maximum_discount_amount is not None:
            discount = min(discount, float(promocode.maximum_discount_amount))

        return min(discount, subtotal)

    async def _get_tax_rate(self, shipping_address) -> float:
        """
        Get tax rate from database based on shipping address
        Returns 0.0 if no tax rate is found in database
        """
        try:
            if not shipping_address:
                logger.info("No shipping address provided, using 0.0 tax rate")
                return 0.0
            
            # Get state/country from address
            state = getattr(shipping_address, 'state', None) or shipping_address.get('state', '')
            country = getattr(shipping_address, 'country', None) or shipping_address.get('country', 'US')
            
            logger.info(f"Looking up tax rate for country: {country}, state: {state}")
            
            # First try to find tax rate with specific province/state
            if state:
                tax_rate_result = await self.db.execute(
                    select(TaxRate).where(
                        and_(
                            TaxRate.country_code == country.upper(),
                            TaxRate.province_code == state.upper(),
                            TaxRate.is_active == True
                        )
                    )
                )
                # country_code+province_code isn't unique-constrained - take the
                # first match instead of scalar_one_or_none().
                tax_rate_record = tax_rate_result.scalars().first()

                if tax_rate_record:
                    logger.info(f"Found state/province tax rate for {country}-{state}: {tax_rate_record.tax_rate} ({tax_rate_record.tax_name})")
                    return float(tax_rate_record.tax_rate)
                else:
                    logger.info(f"No state/province tax rate found for {country}-{state}")

            # If no state-specific rate found, try country-level rate
            tax_rate_result = await self.db.execute(
                select(TaxRate).where(
                    and_(
                        TaxRate.country_code == country.upper(),
                        TaxRate.province_code.is_(None),  # Country-level rate
                        TaxRate.is_active == True
                    )
                )
            )
            tax_rate_record = tax_rate_result.scalars().first()

            if tax_rate_record:
                logger.info(f"Found country tax rate for {country}: {tax_rate_record.tax_rate} ({tax_rate_record.tax_name})")
                return float(tax_rate_record.tax_rate)
            
            # No tax rate found in database
            logger.info(f"No tax rate found in database for {country}-{state}, using 0.0")
            return 0.0
            
        except Exception as e:
            logger.error(f"Error getting tax rate from database: {e}")
            return 0.0
    def _generate_price_update_message(self, price_updates: List[Dict], total_change: float) -> str:
        """
        Generate a user-friendly message about price updates
        """
        total_items = len(price_updates)
        
        if total_items == 1:
            update = price_updates[0]
            if update["price_increased"]:
                if update["is_sale"]:
                    return f"Good news! {update['product_name']} is now on sale for ${update['new_price']:.2f}"
                else:
                    return f"Price updated: {update['product_name']} is now ${update['new_price']:.2f} (was ${update['old_price']:.2f})"
            else:
                return f"Price reduced: {update['product_name']} is now ${update['new_price']:.2f} (was ${update['old_price']:.2f})"
        else:
            if total_change > 0:
                return f"Prices updated for {total_items} items in your cart. Total increase: ${total_change:.2f}"
            elif total_change < 0:
                return f"Great news! Prices reduced for {total_items} items in your cart. You save ${abs(total_change):.2f}!"
            else:
                return f"Prices updated for {total_items} items in your cart."

    async def _send_order_events_with_idempotency(self, order: Order, user_id: UUID, validated_cart_items: List[Dict[str, Any]]):
        """
        Send order-created side effects (confirmation email) after a successful checkout.
        """
        try:
            from services.accounts.email import EmailService

            # Prepare order items for the email template
            order_items = []
            for item in validated_cart_items:
                order_items.append({
                    "name": item.get("product_name", ""),
                    "quantity": item["quantity"],
                    "price": float(item["backend_price"]),
                })

            # order.shipping_address is stored as a plain JSON dict, not a relationship
            shipping_address = {}
            if order.shipping_address:
                shipping_address = {
                    "street": order.shipping_address.get("street"),
                    "city": order.shipping_address.get("city"),
                    "state": order.shipping_address.get("state"),
                    "country": order.shipping_address.get("country"),
                    "postal_code": order.shipping_address.get("postal_code") or order.shipping_address.get("post_code")
                }

            # Send order confirmation email
            user_result = await self.db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            if user:
                await EmailService(self.db).send_order_confirmation_email(
                    recipient_email=user.email,
                    customer_name=user.firstname or user.email,
                    order_number=order.order_number,
                    order_date=order.created_at,
                    total_amount=float(order.total_amount),
                    items=order_items,
                    shipping_address=shipping_address
                )
            
            # Order payment event handled by hybrid task system
            
            logger.info(f"Successfully published order events for order {order.id} using new event system")
            
        except Exception as e:
            logger.error(f"Failed to publish order events using new event system: {e}")
            raise
    async def tracking(self, order_id: UUID, user_id: UUID) -> Dict[str, Any]:
        """Get order tracking information for authenticated user"""
        from core.exceptions import APIException
        try:
            # Get order with tracking events
            query = select(Order).where(
                and_(Order.id == order_id, Order.user_id == user_id)
            ).options(
                selectinload(Order.tracking_events)
            )
            
            result = await self.db.execute(query)
            order = result.scalar_one_or_none()
            
            if not order:
                raise APIException(status_code=404, message="Order not found")
            
            # Format tracking events
            tracking_events = []
            for event in order.tracking_events:
                tracking_events.append({
                    "id": str(event.id),
                    "status": event.status,
                    "description": event.description,
                    "location": event.location,
                    "timestamp": event.created_at.isoformat() if event.created_at else None
                })
            
            # Sort events by timestamp (newest first)
            tracking_events.sort(key=lambda x: x["timestamp"] or "", reverse=True)
            
            return {
                "order_id": str(order.id),
                "order_number": order.order_number,
                "status": order.order_status,
                "tracking_number": order.tracking_number,
                "carrier": order.carrier,
                "estimated_delivery": self._calculate_estimated_delivery(order),
                "tracking_events": tracking_events,
                "shipping_address": order.shipping_address
            }
            
        except APIException:
            raise
        except Exception as e:
            logger.error(f"Failed to get order tracking for order {order_id}: {e}")
            raise APIException(
                status_code=500,
                message="Failed to retrieve tracking information"
            )

    async def payments(self, order_id: UUID, user_id: UUID) -> Dict[str, Any]:
        """Get payment intents and transactions for an order (authenticated, owner only)"""
        from core.exceptions import APIException
        from models.commerce.payments import PaymentIntent, Transaction
        try:
            query = select(Order).where(
                and_(Order.id == order_id, Order.user_id == user_id)
            ).options(
                selectinload(Order.payment_intents),
                selectinload(Order.transactions)
            )

            result = await self.db.execute(query)
            order = result.scalar_one_or_none()

            if not order:
                raise APIException(status_code=404, message="Order not found")

            return {
                "order_id": str(order.id),
                "order_number": order.order_number,
                "payment_status": order.payment_status,
                "payment_intents": [intent.to_dict() for intent in order.payment_intents],
                "transactions": [txn.to_dict() for txn in order.transactions],
            }

        except APIException:
            raise
        except Exception as e:
            logger.error(f"Failed to get payments for order {order_id}: {e}")
            raise APIException(
                status_code=500,
                message="Failed to retrieve payment information"
            )

    async def tracking_public(self, order_id: str) -> Dict[str, Any]:
        """Get order tracking information without authentication (public endpoint)"""
        try:
            # Try to parse as UUID first, if fails treat as order_number
            try:
                order_uuid = UUID(order_id)
                query = select(Order).where(Order.id == order_uuid).options(
                    selectinload(Order.tracking_events)
                )
            except ValueError:
                # Not a UUID, treat as order_number
                query = select(Order).where(Order.order_number == order_id).options(
                    selectinload(Order.tracking_events)
                )

            result = await self.db.execute(query)
            order = result.scalar_one_or_none()

            if not order:
                raise HTTPException(status_code=404, detail="Order not found")
            
            # Only return limited information for public access
            tracking_events = []
            for event in order.tracking_events:
                # Only include public-safe tracking events
                if event.status in ["confirmed", "processing", "shipped", "out_for_delivery", "delivered"]:
                    tracking_events.append({
                        "status": event.status,
                        "description": event.description,
                        "location": event.location,
                        "timestamp": event.created_at.isoformat() if event.created_at else None
                    })
            
            # Sort events by timestamp (newest first)
            tracking_events.sort(key=lambda x: x["timestamp"] or "", reverse=True)
            
            return {
                "order_number": order.order_number,
                "status": order.order_status,
                "tracking_number": order.tracking_number,
                "carrier": order.carrier,
                "estimated_delivery": self._calculate_estimated_delivery(order),
                "tracking_events": tracking_events
                # Note: No shipping address or sensitive info for public access
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get public order tracking for order {order_id}: {e}")
            raise HTTPException(
                status_code=404,
                detail="Order not found or tracking information unavailable"
            )

    async def reorder(self, order_id: UUID, user_id: UUID) -> OrderResponse:
        """Create a new order from an existing order"""
        try:
            # Get the original order with items
            query = select(Order).where(
                and_(Order.id == order_id, Order.user_id == user_id)
            ).options(
                selectinload(Order.items).selectinload(OrderItem.variant)
            )
            
            result = await self.db.execute(query)
            original_order = result.scalar_one_or_none()
            
            if not original_order:
                raise HTTPException(status_code=404, detail="Original order not found")
            
            # Clear user's current cart
            cart_service = CartService(self.db)
            await cart_service.clear_cart(user_id)
            
            # Add items from original order to cart
            for item in original_order.items:
                # Check if variant still exists and is available
                variant_query = select(ProductVariant).where(ProductVariant.id == item.variant_id)
                variant_result = await self.db.execute(variant_query)
                variant = variant_result.scalar_one_or_none()
                
                if variant and variant.is_active:
                    # Check stock availability
                    stock_check = await self.inventory_service.check_stock(
                        variant_id=item.variant_id,
                        quantity=item.quantity
                    )
                    
                    # Add to cart with available quantity
                    quantity_to_add = min(item.quantity, stock_check.get("current_stock", 0))
                    if quantity_to_add > 0:
                        await cart_service.add_to_cart(
                            user_id=user_id,
                            variant_id=item.variant_id,
                            quantity=quantity_to_add
                        )
            
            # Get updated cart
            cart = await cart_service.get_or_create(user_id)
            
            if not cart.items:
                raise HTTPException(
                    status_code=400,
                    detail="No items from the original order are currently available"
                )
            
            return {
                "message": "Items added to cart successfully",
                "cart_items": len(cart.items),
                "original_order_id": str(order_id),
                "cart_id": str(cart.id)
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to reorder from order {order_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail="Failed to create reorder"
            )

    async def invoice(self, order_id: UUID, user_id: UUID) -> Dict[str, Any]:
        """Generate invoice for an order"""
        try:
            # Get order with items
            query = select(Order).where(
                and_(Order.id == order_id, Order.user_id == user_id)
            ).options(
                selectinload(Order.items).selectinload(OrderItem.variant).selectinload(ProductVariant.product),
                selectinload(Order.user)
            )
            
            result = await self.db.execute(query)
            order = result.scalar_one_or_none()
            
            if not order:
                raise HTTPException(status_code=404, detail="Order not found")
            
            # Use invoice generator utility
            from core.utils.invoice_generator import InvoiceGenerator
            
            invoice_generator = InvoiceGenerator()
            
            # Prepare order data for invoice
            customer_name = "Customer"
            if order.user:
                firstname = order.user.firstname or ""
                lastname = order.user.lastname or ""
                customer_name = f"{firstname} {lastname}".strip() or order.user.email or "Customer"
            
            order_data = {
                "order_id": str(order.id),
                "order_number": order.order_number,
                "order_date": order.created_at,
                "customer": {
                    "name": customer_name,
                    "email": order.user.email if order.user else "N/A",
                    "phone": order.user.phone if order.user and order.user.phone else None
                },
                "billing_address": order.billing_address,
                "shipping_address": order.shipping_address,
                "items": [
                    {
                        "name": item.variant.product.name if item.variant and item.variant.product else "Unknown Product",
                        "variant_name": item.variant.name if item.variant else "",
                        "quantity": item.quantity,
                        "price": item.price_per_unit,
                        "total": item.total_price
                    }
                    for item in order.items
                ],
                "subtotal": order.subtotal,
                "tax_amount": order.tax_amount,
                "shipping_amount": order.shipping_cost,
                "discount_amount": order.discount_amount,
                "total_amount": order.total_amount,
                "currency": order.currency,
                "payment_status": order.payment_status
            }
            
            # Generate invoice
            invoice_result = await invoice_generator.generate_invoice(order_data)
            
            return invoice_result
            
        except HTTPException:
            raise
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to generate invoice for order {order_id}: {e}")
            logger.error(f"Order data: {order_data if 'order_data' in locals() else 'Not available'}")

            # Check if it's a system library dependency error
            if 'libgobject' in error_msg or 'cannot load library' in error_msg or 'dyld' in error_msg or 'GTK' in error_msg:
                raise HTTPException(
                    status_code=503,
                    detail="PDF generation is not available on this server. System libraries (GTK+) are missing. Please install the required dependencies or use a different server configuration."
                )

            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate invoice: {str(e)}"
            )

    async def add_note(self, order_id: UUID, user_id: UUID, note: str) -> Dict[str, Any]:
        """Add a customer note to an order"""
        try:
            # Get order
            query = select(Order).where(
                and_(Order.id == order_id, Order.user_id == user_id)
            )
            
            result = await self.db.execute(query)
            order = result.scalar_one_or_none()
            
            if not order:
                raise HTTPException(status_code=404, detail="Order not found")
            
            # Add note to customer_notes (append if existing)
            if order.customer_notes:
                timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                order.customer_notes += f"\n\n[{timestamp}] {note}"
            else:
                timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                order.customer_notes = f"[{timestamp}] {note}"
            
            await self.db.commit()
            await self.db.refresh(order)
            
            return {
                "order_id": str(order.id),
                "note_added": note,
                "timestamp": timestamp,
                "all_notes": order.customer_notes
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to add note to order {order_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail="Failed to add order note"
            )

    async def notes(self, order_id: UUID, user_id: UUID) -> Dict[str, Any]:
        """Get all customer notes for an order"""
        try:
            # Get order
            query = select(Order).where(
                and_(Order.id == order_id, Order.user_id == user_id)
            )
            
            result = await self.db.execute(query)
            order = result.scalar_one_or_none()
            
            if not order:
                raise HTTPException(status_code=404, detail="Order not found")
            
            # Parse notes if they exist
            notes = []
            if order.customer_notes:
                # Split notes by timestamp pattern
                import re
                note_pattern = r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (.*?)(?=\n\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]|$)'
                matches = re.findall(note_pattern, order.customer_notes, re.DOTALL)
                
                for timestamp_str, note_text in matches:
                    notes.append({
                        "timestamp": timestamp_str,
                        "note": note_text.strip()
                    })
            
            return {
                "order_id": str(order.id),
                "notes": notes,
                "total_notes": len(notes)
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get notes for order {order_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve order notes"
            )

    async def get_note(self, order_id: UUID, user_id: UUID, note_index: int) -> Optional[Dict[str, Any]]:
        """Get a specific note by index"""
        try:
            notes_result = await self.notes(order_id, user_id)
            notes = notes_result.get("notes", [])
            if 0 <= note_index < len(notes):
                return {
                    "order_id": str(order_id),
                    "note_index": note_index,
                    **notes[note_index]
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get note {note_index} for order {order_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to retrieve note")

    async def update_note(self, order_id: UUID, user_id: UUID, note_index: int, new_note: str) -> Dict[str, Any]:
        """Update a specific note by index"""
        try:
            query = select(Order).where(Order.id == order_id, Order.user_id == user_id)
            result = await self.db.execute(query)
            order = result.scalar_one_or_none()
            if not order:
                raise HTTPException(status_code=404, detail="Order not found")
            
            notes_result = await self.notes(order_id, user_id)
            notes = notes_result.get("notes", [])
            if not (0 <= note_index < len(notes)):
                raise HTTPException(status_code=404, detail="Note not found")
            
            # Rebuild notes with updated one
            updated_notes = []
            for i, note in enumerate(notes):
                if i == note_index:
                    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                    updated_notes.append(f"[{timestamp}] {new_note}")
                else:
                    updated_notes.append(f"[{note['timestamp']}] {note['note']}")
            
            order.customer_notes = "\n\n".join(updated_notes)
            await self.db.commit()
            await self.db.refresh(order)
            
            return {
                "order_id": str(order_id),
                "note_index": note_index,
                "updated_note": new_note,
                "timestamp": datetime.utcnow().isoformat()
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to update note {note_index} for order {order_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to update note")

    async def delete_note(self, order_id: UUID, user_id: UUID, note_index: int) -> bool:
        """Delete a specific note by index"""
        try:
            query = select(Order).where(Order.id == order_id, Order.user_id == user_id)
            result = await self.db.execute(query)
            order = result.scalar_one_or_none()
            if not order:
                raise HTTPException(status_code=404, detail="Order not found")
            
            notes_result = await self.notes(order_id, user_id)
            notes = notes_result.get("notes", [])
            if not (0 <= note_index < len(notes)):
                return False
            
            # Rebuild notes without deleted one
            updated_notes = []
            for i, note in enumerate(notes):
                if i != note_index:
                    updated_notes.append(f"[{note['timestamp']}] {note['note']}")
            
            order.customer_notes = "\n\n".join(updated_notes) if updated_notes else None
            await self.db.commit()
            await self.db.refresh(order)
            
            return True
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to delete note {note_index} for order {order_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to delete note")

    def _calculate_estimated_delivery(self, order: Order) -> Optional[str]:
        """Calculate estimated delivery date based on order status and shipping method"""
        try:
            if order.delivered_at:
                return order.delivered_at.isoformat()
            
            if order.order_status in ["cancelled", "refunded"]:
                return None
            
            # Base delivery estimate on shipping method and current status
            base_days = 5  # Default delivery time
            
            # Adjust based on shipping method
            if order.shipping_method:
                shipping_method_lower = order.shipping_method.lower()
                if "express" in shipping_method_lower or "overnight" in shipping_method_lower:
                    base_days = 1
                elif "priority" in shipping_method_lower or "2-day" in shipping_method_lower:
                    base_days = 2
                elif "standard" in shipping_method_lower:
                    base_days = 5
                elif "economy" in shipping_method_lower:
                    base_days = 7
            
            # Calculate from appropriate date
            if order.shipped_at:
                estimated_date = order.shipped_at + timedelta(days=base_days)
            elif order.confirmed_at:
                estimated_date = order.confirmed_at + timedelta(days=base_days + 2)  # Add processing time
            else:
                estimated_date = order.created_at + timedelta(days=base_days + 3)  # Add confirmation + processing time
            
            return estimated_date.isoformat()
            
        except Exception as e:
            logger.error(f"Failed to calculate estimated delivery for order {order.id}: {e}")
            return None

    
    async def deliver(self, order_id: str, notes: Optional[str] = None) -> dict:
        """Mark order as delivered (admin only)."""
        return await self.update_status(
            order_id=UUID(order_id),
            status="delivered",
            description=notes
        )

    async def ship(self, order_id: str, carrier: Optional[str], tracking_number: Optional[str]) -> dict:
        """Ship order (admin only)."""
        return await self.update_status(
            order_id=UUID(order_id),
            status="shipped",
            carrier_name=carrier,
            tracking_number=tracking_number
        )

    async def get_statistics(self, date_from: Optional[str] = None, date_to: Optional[str] = None) -> dict:
        """Get order statistics (admin only)."""
        from sqlalchemy import func

        # Build base query
        query = select(Order)

        if date_from:
            try:
                from_date = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                query = query.where(Order.created_at >= from_date)
            except ValueError:
                pass

        if date_to:
            try:
                to_date = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                query = query.where(Order.created_at <= to_date)
            except ValueError:
                pass

        # Get counts by status
        status_query = select(Order.order_status, func.count(Order.id)).group_by(Order.order_status)
        if date_from:
            try:
                from_date = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                status_query = status_query.where(Order.created_at >= from_date)
            except ValueError:
                pass
        if date_to:
            try:
                to_date = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                status_query = status_query.where(Order.created_at <= to_date)
            except ValueError:
                pass

        status_result = await self.db.execute(status_query)
        status_counts = {status: count for status, count in status_result.all()}

        # Get total revenue
        revenue_query = select(func.sum(Order.total_amount)).where(Order.order_status.notin_(["cancelled", "refunded"]))
        if date_from:
            try:
                from_date = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                revenue_query = revenue_query.where(Order.created_at >= from_date)
            except ValueError:
                pass
        if date_to:
            try:
                to_date = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                revenue_query = revenue_query.where(Order.created_at <= to_date)
            except ValueError:
                pass

        revenue_result = await self.db.execute(revenue_query)
        total_revenue = revenue_result.scalar() or 0

        # Get total orders count
        count_query = select(func.count(Order.id))
        if date_from:
            try:
                from_date = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                count_query = count_query.where(Order.created_at >= from_date)
            except ValueError:
                pass
        if date_to:
            try:
                to_date = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                count_query = count_query.where(Order.created_at <= to_date)
            except ValueError:
                pass

        count_result = await self.db.execute(count_query)
        total_orders = count_result.scalar() or 0

        return {
            "total_orders": total_orders,
            "total_revenue": float(total_revenue),
            "status_breakdown": status_counts,
            "date_range": {
                "from": date_from,
                "to": date_to
            }
        }