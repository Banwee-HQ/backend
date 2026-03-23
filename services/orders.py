"""
Comprehensive Order Service with Advanced Pricing and Security
Handles complete order lifecycle with backend-only price calculations
"""
import hashlib
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, delete
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, BackgroundTasks
from models.orders import Order, OrderItem, TrackingEvent, PaymentStatus, OrderStatus
from models.user import User
from services.email import send_order_confirmation_email
from models.cart import Cart, CartItem
from models.user import User, Address
from models.product import ProductVariant
from models.shipping import ShippingMethod
from models.payments import PaymentMethod
from models.tax_rates import TaxRate
from schemas.orders import OrderResponse, OrderItemResponse, CheckoutRequest, OrderCreate
from schemas.inventory import StockAdjustmentCreate
from services.cart import CartService
from services.payments import PaymentService
from services.inventory import InventoryService 
from services.tax import TaxService
from services.shipping import ShippingService
from services.discounts import DiscountEngine
from models.inventories import Inventory
from uuid import UUID
from core.utils.uuid_utils import uuid7
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from decimal import Decimal, ROUND_HALF_UP
from core.config import settings
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)


class PricingCalculationResult:
    """Result of comprehensive pricing calculation"""
    def __init__(
        self,
        subtotal: Decimal,
        shipping_cost: Decimal,
        tax_amount: Decimal,
        tax_rate: float,
        discount_amount: Decimal,
        total_amount: Decimal,
        currency: str = "USD",
        breakdown: Dict[str, Any] = None
    ):
        self.subtotal = subtotal
        self.shipping_cost = shipping_cost
        self.tax_amount = tax_amount
        self.tax_rate = tax_rate
        self.discount_amount = discount_amount
        self.total_amount = total_amount
        self.currency = currency
        self.breakdown = breakdown or {}


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

    async def calculate_comprehensive_pricing(
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
        shipping_method = await self.shipping_service.get_shipping_method_by_id(shipping_method_id)
        if shipping_method and shipping_method.is_active:
            shipping_cost = Decimal(str(shipping_method.price))
            logger.info(f"Shipping cost: ${shipping_cost} ({shipping_method.name})")
        
        # Step 3: Calculate tax based on shipping address
        tax_rate = await self.tax_service.get_tax_rate(
            shipping_address.country or "US",
            shipping_address.state
        )
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
                if validation_result.is_valid:
                    discount = validation_result.discount
                    if discount.type == "PERCENTAGE":
                        discount_amount = (subtotal * Decimal(str(discount.value / 100))).quantize(
                            Decimal('0.01'), rounding=ROUND_HALF_UP
                        )
                        if discount.maximum_discount:
                            discount_amount = min(discount_amount, Decimal(str(discount.maximum_discount)))
                    elif discount.type == "FIXED_AMOUNT":
                        discount_amount = min(Decimal(str(discount.value)), subtotal)
                    elif discount.type == "FREE_SHIPPING":
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
            tax_rate=tax_rate,
            discount_amount=discount_amount,
            total_amount=total_amount,
            currency=currency,
            breakdown=breakdown
        )

    async def validate_checkout_requirements(
        self,
        user_id: UUID,
        request: CheckoutRequest
    ) -> Dict[str, Any]:
        """
        Comprehensive checkout validation with detailed error reporting
        """
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
                return validation_result
            
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
                return validation_result
            
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
                return validation_result
            
            # Step 3: Validate shipping method
            shipping_method = await self.shipping_service.get_shipping_method_by_id(request.shipping_method_id)
            if not shipping_method or not shipping_method.is_active:
                validation_result['valid'] = False
                validation_result['can_proceed'] = False
                validation_result['errors'].append({
                    'field': 'shipping_method_id',
                    'message': 'Invalid or inactive shipping method'
                })
                return validation_result
            
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
                return validation_result
            
            # Step 5: Calculate comprehensive pricing
            pricing = await self.calculate_comprehensive_pricing(
                cart.items,
                shipping_address,
                request.shipping_method_id,
                getattr(request, 'discount_code', None),
                getattr(request, 'currency', 'USD')
            )
            validation_result['pricing'] = pricing.breakdown
            
            # Step 6: Validate frontend price if provided
            if hasattr(request, 'frontend_calculated_total') and request.frontend_calculated_total:
                frontend_total = Decimal(str(request.frontend_calculated_total))
                backend_total = pricing.total_amount
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
            return validation_result
            
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
            return validation_result

    async def place_order_with_comprehensive_validation(
        self, 
        user_id: UUID, 
        request: CheckoutRequest, 
        background_tasks: BackgroundTasks,
        idempotency_key: Optional[str] = None
    ) -> OrderResponse:
        """
        Place order with comprehensive validation and security checks
        """
        logger.info(f"Processing order for user {user_id}")
        
        # Step 1: Comprehensive validation
        validation_result = await self.validate_checkout_requirements(user_id, request)
        
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
            # Generate order number for payment reference
            order_number = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{uuid7().hex[:8].upper()}"
            temp_order_id = uuid7()  # Temporary ID for payment processing
            
            # Process payment with Stripe using backend-calculated total
            payment_service = PaymentService(self.db)
            payment_idempotency_key = (
                f"payment_{temp_order_id}_{idempotency_key}" if idempotency_key else f"payment_{temp_order_id}"
            )

            logger.info(f"Processing payment for order {order_number}, amount: {pricing['total']}")
            
            payment_result = await payment_service.process_payment_idempotent(
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
            
            logger.info(f"Payment successful for order {order_number}, creating order...")
            
            # Step 4: Create order (ONLY after successful payment)
            order = Order(
                id=temp_order_id,  # Use the same ID we used for payment
                order_number=order_number,
                user_id=user_id,
                order_status="confirmed",  # Start as confirmed since payment succeeded
                payment_status="paid",  # Payment already succeeded
                fulfillment_status="unfulfilled",
                subtotal=pricing['subtotal'],
                shipping_cost=pricing['shipping']['cost'],
                tax_amount=pricing['tax']['amount'],
                tax_rate=pricing['tax']['rate'],
                total_amount=pricing['total'],
                currency=pricing['currency'],
                shipping_method=shipping_method.name,
                billing_address={
                    'street': shipping_address.street,
                    'city': shipping_address.city,
                    'state': shipping_address.state,
                    'country': shipping_address.country,
                    'post_code': shipping_address.post_code
                },
                shipping_address={
                    'street': shipping_address.street,
                    'city': shipping_address.city,
                    'state': shipping_address.state,
                    'country': shipping_address.country,
                    'post_code': shipping_address.post_code
                },
                notes=request.notes
            )
            self.db.add(order)
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
                    send_order_confirmation_email(
                        background_tasks=background_tasks,
                        to_email=user.email,
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
                "items_count": len(order.items),
                "payment_status": "completed",
                "milestone": "revenue"
            })
            
            # Return order response using the items we collected
            return OrderResponse(
                id=order.id,
                user_id=user_id,
                status=order.order_status,
                total_amount=order.total_amount,
                subtotal=order.subtotal,
                tax_amount=order.tax_amount,
                shipping_amount=order.shipping_cost,
                discount_amount=Decimal('0.00'),  # Can be updated if discount is used
                currency=order.currency,
                created_at=order.created_at.isoformat() if order.created_at else datetime.utcnow().isoformat(),
                tracking_number=None,
                estimated_delivery=None,
                items=[
                    OrderItemResponse(
                        id=item.id,
                        variant_id=item.variant_id,
                        quantity=item.quantity,
                        price_per_unit=item.price_per_unit,
                        total_price=item.total_price
                    ) for item in order_items_list
                ]
            )
            
        except Exception as e:
            logger.error(f"Order creation failed for user {user_id}: {e}")
            # Session will auto-rollback on exception due to the context manager
            raise HTTPException(
                status_code=500,
                detail="Order creation failed due to system error"
            )
        
        # STEP 3: Proceed with regular order placement
        return await self.place_order_with_idempotency(user_id, request, background_tasks, idempotency_key)

    async def place_order_with_idempotency(
        self, 
        user_id: UUID, 
        request: CheckoutRequest, 
        background_tasks: BackgroundTasks,
        idempotency_key: Optional[str] = None
    ) -> OrderResponse:
        """
        Place an order with idempotency protection
        Prevents duplicate orders from being created
        """
        # Generate idempotency key if not provided
        if not idempotency_key:
            # Create deterministic key based on user, cart state, and timestamp
            cart_service = CartService(self.db)
            cart = await cart_service.get_or_create_cart(user_id)
            
            # Create hash of cart contents + user + shipping details
            cart_hash = self._generate_cart_hash(cart, request)
            idempotency_key = f"order_{user_id}_{cart_hash}"
        
        # Check if order already exists with this idempotency key (with lock to prevent duplicates)
        existing_order = await self.db.execute(
            select(Order).where(Order.idempotency_key == idempotency_key).with_for_update()
        )
        existing = await existing_order.scalar_one_or_none()
        
        if existing:
            # Return existing order
            return await self._convert_order_to_response(existing)
        
        # If no existing order, delegate to the main place_order method
        return await self.place_order(user_id, request, background_tasks, idempotency_key)
    
    async def request_refund(
        self, 
        order_id: UUID, 
        user_id: UUID, 
        refund_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Request a refund for an order
        Delegates to the RefundService for comprehensive refund processing
        """
        try:
            from services.refunds import RefundService
            from schemas.refunds import RefundRequest
            
            # Create refund service
            refund_service = RefundService(self.db)
            
            # Convert refund_data to RefundRequest schema
            refund_request = RefundRequest(**refund_data)
            
            # Process refund request
            refund_response = await refund_service.request_refund(
                user_id=user_id,
                order_id=order_id,
                refund_request=refund_request
            )
            
            return refund_response.dict()
            
        except Exception as e:
            logger.error(f"Failed to request refund for order {order_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process refund request: {str(e)}"
            )

    async def place_order(
        self, 
        user_id: UUID, 
        request: CheckoutRequest, 
        background_tasks: BackgroundTasks,
        idempotency_key: Optional[str] = None
    ) -> OrderResponse:
        """
        Place an order from the user's cart with comprehensive validation and atomic operations
        ALWAYS validates cart before proceeding with checkout
        """
        # Generate idempotency key if not provided
        if not idempotency_key:
            cart_service = CartService(self.db)
            cart = await cart_service.get_or_create_cart(user_id)
            cart_hash = self._generate_cart_hash(cart, request)
            idempotency_key = f"order_{user_id}_{cart_hash}"
        
        # Use distributed lock to prevent duplicate orders for same user/cart combination
        if self.lock_service:
            order_lock = self.lock_service.get_custom_lock(f"order_creation_{user_id}_{idempotency_key}", timeout=60)
            async with order_lock:
                return await self._perform_order_placement(user_id, request, background_tasks, idempotency_key)
        else:
            # Fallback if Redis unavailable
            logger.warning(f"Redis lock service unavailable, proceeding without order creation lock for user {user_id}")
            return await self._perform_order_placement(user_id, request, background_tasks, idempotency_key)

    async def _perform_order_placement(
        self,
        user_id: UUID,
        request: CheckoutRequest,
        background_tasks: BackgroundTasks,
        idempotency_key: str
    ) -> OrderResponse:
        """Internal method to perform order placement with all validations"""
        # Check for existing order with this idempotency key
        existing_order = await self.db.execute(
            select(Order).where(Order.idempotency_key == idempotency_key)
        )
        existing = await existing_order.scalar_one_or_none()
        
        if existing:
            logger.info(f"Returning existing order for idempotency key: {idempotency_key}")
            return await self._convert_order_to_response(existing)
        
        # Start atomic transaction for entire checkout process
        async with self.db.begin():
            try:
                # STEP 1: MANDATORY CART VALIDATION - Never skip this step
                cart_service = CartService(self.db)
                
                # Get location from shipping address for tax calculation
                country_code = "US"
                province_code = None
                if hasattr(request, 'shipping_address_id') and request.shipping_address_id:
                    shipping_address_result = await self.db.execute(
                        select(Address).where(Address.id == request.shipping_address_id)
                    )
                    shipping_address = shipping_address_result.scalar_one_or_none()
                    if shipping_address:
                        country_code = shipping_address.country or "US"
                        province_code = shipping_address.state
                
                # Always validate cart first - this is critical for data integrity
                validation_result = await cart_service.validate_cart(
                    user_id,
                    country_code=country_code,
                    province_code=province_code
                )
                
                if not validation_result.get("valid", False) or not validation_result.get("can_checkout", False):
                    # Cart validation failed - return detailed error
                    error_issues = [issue for issue in validation_result.get("issues", []) if issue.get("severity") == "error"]
                    if error_issues:
                        error_messages = [issue["message"] for issue in error_issues]
                        raise HTTPException(
                            status_code=400, 
                            detail={
                                "message": "Cart validation failed. Please review and update your cart.",
                                "issues": error_issues,
                                "validation_summary": validation_result.get("summary", {}),
                                "error_count": len(error_issues)
                            }
                        )
                    else:
                        raise HTTPException(status_code=400, detail="Cart is empty or invalid")
                
                # Get validated cart
                cart = validation_result["cart"]
                
                # Check if cart has items after validation
                active_items = [item for item in cart.items if not getattr(item, 'saved_for_later', False)]
                if not active_items:
                    raise HTTPException(status_code=400, detail="No items available for checkout after validation")
                
                # Log validation results for monitoring
                validation_summary = validation_result.get("summary", {})
                if validation_summary.get("price_updates", 0) > 0 or validation_summary.get("stock_adjustments", 0) > 0:
                    logger.info(f"Cart validation updated items for user {user_id}: {validation_summary}")
                
                # STEP 2: BACKEND PRICE VALIDATION - Never trust frontend prices
                price_validation_result = await self._validate_and_recalculate_prices(cart)
                if not price_validation_result["valid"]:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Price validation failed: {price_validation_result['message']}"
                    )
                
                # Use backend-calculated prices, not frontend prices
                validated_cart_items = price_validation_result["validated_items"]
                backend_calculated_total = price_validation_result["total_amount"]
                price_updates = price_validation_result.get("price_updates", [])
                
                # STEP 3: CHECK STOCK AVAILABILITY (optimized for Checkout)
                stock_validation_results = []
                for item in active_items:
                    stock_check = await self.inventory_service.check_stock_availability(
                        variant_id=item.variant.id,
                        quantity=item.quantity
                    )
                    
                    if not stock_check.get("available", False):
                        stock_validation_results.append({
                            "variant_id": item.variant.id,
                            "product_name": item.variant.product.name if item.variant and item.variant.product else "Unknown Product",
                            "requested": item.quantity,
                            "available": stock_check.get("current_stock", 0),
                            "status": stock_check.get("stock_status", "out_of_stock"),
                            "message": stock_check.get("message", "Out of stock")
                        })
                
                # If any stock issues, return detailed error
                if stock_validation_results:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "message": "Stock validation failed",
                            "stock_issues": stock_validation_results,
                            "error_type": "STOCK_UNAVAILABLE"
                        }
                    )
                
                # STEP 4: VALIDATE CHECKOUT DEPENDENCIES
                # Verify shipping address exists
                shipping_address = await self.db.execute(
                    select(Address).where(
                        and_(Address.id == request.shipping_address_id, Address.user_id == user_id))
                )
                shipping_address = shipping_address.scalar_one_or_none()
                if not shipping_address:
                    raise HTTPException(status_code=404, detail="Shipping address not found")

                # Verify shipping method exists and get its cost
                shipping_method = await self.db.execute(
                    select(ShippingMethod).where(ShippingMethod.id == request.shipping_method_id)
                )
                shipping_method = shipping_method.scalar_one_or_none()
                if not shipping_method:
                    raise HTTPException(status_code=404, detail="Shipping method not found")

                # Verify payment method exists
                payment_method = await self.db.execute(
                    select(PaymentMethod).where(and_(PaymentMethod.id == request.payment_method_id, PaymentMethod.user_id == user_id))
                )
                payment_method = payment_method.scalar_one_or_none() 
            except HTTPException:
                # Re-raise HTTP exceptions to be handled by outer transaction
                raise
        
        # Initialize payment_method to None if not set, and handle validation
        if not request.payment_method_id:
            payment_method = None
        
        if payment_method is None: # This covers both cases: not provided, or provided but not found
            raise HTTPException(status_code=404, detail="Payment method not found")

        # STEP 4: CALCULATE FINAL TOTAL (backend calculation only)
        final_total = await self._calculate_final_order_total(
            validated_cart_items, 
            shipping_method, 
            shipping_address
        )

        # VALIDATION: Ensure total calculation is correct
        calculated_total = (
            final_total["subtotal"] + 
            final_total["shipping_cost"] + 
            final_total["tax_amount"] - 
            final_total["discount_amount"]
        )
        
        if abs(calculated_total - final_total["total_amount"]) > 0.01:
            logger.error(f"Order total calculation mismatch for user {user_id}: "
                        f"calculated={calculated_total:.2f}, "
                        f"returned={final_total['total_amount']:.2f}")
            raise HTTPException(
                status_code=500, 
                detail="Order total calculation error. Please try again."
            )

        # STEP 5: ATOMIC TRANSACTION FOR ORDER CREATION
        try:
            # Begin transaction - all operations below must succeed or all will be rolled back
            async with self.db.begin():
                # Generate order number
                order_number = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid7())[:8].upper()}"
                
                # Extract totals from final_total calculation
                subtotal = final_total["subtotal"]
                tax_amount = final_total["tax_amount"]
                shipping_amount = final_total["shipping_cost"]
                discount_amount = final_total["discount_amount"]
                total_amount = final_total["total_amount"]
                
                # Convert addresses to dict format for JSONB storage
                billing_address_dict = {
                    "street": shipping_address.street,
                    "city": shipping_address.city,
                    "state": shipping_address.state,
                    "country": shipping_address.country,
                    "postal_code": shipping_address.post_code,
                }
                
                # Use shipping address as billing address if no separate billing address
                shipping_address_dict = billing_address_dict.copy()
                
                # Create order with backend-calculated prices and idempotency key
                order = Order(
                    user_id=user_id,
                    status="pending",
                    order_number=order_number,
                    subtotal=subtotal,
                    tax_amount=tax_amount,
                    shipping_cost=shipping_amount,
                    discount_amount=discount_amount,
                    total_amount=total_amount,
                    currency=request.currency or "USD",  # Use user's currency from frontend
                    shipping_method=shipping_method.name,
                    tracking_number=None,
                    carrier=None,
                    billing_address=billing_address_dict,
                    shipping_address=shipping_address_dict,
                    shipping_address_id=request.shipping_address_id,
                    shipping_method_id=request.shipping_method_id,
                    payment_method_id=request.payment_method_id,
                    promocode_id=getattr(cart, 'promocode_id', None),
                    notes=request.notes,
                    idempotency_key=idempotency_key,
                    payment_status="pending",
                    fulfillment_status="unfulfilled",
                    order_status="pending",
                    source="web"
                )
                
                # CRITICAL VALIDATION: Ensure order total is correct before saving
                order_calculated_total = order.subtotal + order.shipping_cost + order.tax_amount - order.discount_amount
                
                # ALWAYS log order creation for debugging
                logger.info(f"🔍 ORDER CREATION - User {user_id}:")
                logger.info(f"   Subtotal: ${order.subtotal:.2f}")
                logger.info(f"   Shipping: ${order.shipping_cost:.2f}")
                logger.info(f"   Tax:      ${order.tax_amount:.2f}")
                logger.info(f"   Discount: ${order.discount_amount:.2f}")
                logger.info(f"   Total:    ${order.total_amount:.2f}")
                logger.info(f"   Calculated: ${order_calculated_total:.2f}")
                
                if abs(order_calculated_total - order.total_amount) > 0.01:
                    logger.error(f"❌ ORDER TOTAL VALIDATION FAILED for user {user_id}:")
                    logger.error(f"  Calculated: ${order_calculated_total:.2f}")
                    logger.error(f"  Set total:  ${order.total_amount:.2f}")
                    logger.error(f"  Subtotal:   ${order.subtotal:.2f}")
                    logger.error(f"  Shipping:   ${order.shipping_cost:.2f}")
                    logger.error(f"  Tax:        ${order.tax_amount:.2f}")
                    logger.error(f"  Discount:   ${order.discount_amount:.2f}")
                    logger.error(f"  Difference: ${abs(order_calculated_total - order.total_amount):.2f}")
                    
                    # Write to a debug file as well
                    with open("/tmp/order_validation_errors.log", "a") as f:
                        f.write(f"{datetime.utcnow()}: ORDER VALIDATION FAILED\n")
                        f.write(f"  User: {user_id}\n")
                        f.write(f"  Calculated: ${order_calculated_total:.2f}\n")
                        f.write(f"  Set total:  ${order.total_amount:.2f}\n")
                        f.write(f"  Difference: ${abs(order_calculated_total - order.total_amount):.2f}\n\n")
                    
                    raise HTTPException(
                        status_code=500, 
                        detail="Order total calculation validation failed. Please try again."
                    )
                else:
                    logger.info(f"✅ Order total validation PASSED")
                    # Write success to debug file too
                    with open("/tmp/order_validation_success.log", "a") as f:
                        f.write(f"{datetime.utcnow()}: ORDER VALIDATION PASSED\n")
                        f.write(f"  User: {user_id}\n")
                        f.write(f"  Total: ${order.total_amount:.2f}\n\n")
                
                self.db.add(order)
                await self.db.flush()  # Get order ID without committing

                # Create order items with validated backend prices and atomic stock operations
                for validated_item in validated_cart_items:
                    # Atomically check and decrement stock in single operation
                    try:
                        stock_result = await self.inventory_service.decrement_stock_on_purchase(
                            variant_id=validated_item["variant_id"],
                            quantity=validated_item["quantity"],
                            location_id=None,  # Will be determined by service
                            order_id=order.id,
                            user_id=user_id
                        )
                        
                        if not stock_result["success"]:
                            raise HTTPException(
                                status_code=400, 
                                detail=f"Insufficient stock for variant {validated_item['variant_id']}: {stock_result.get('message', 'Stock unavailable')}"
                            )
                        
                        order_item = OrderItem(
                            order_id=order.id,
                            variant_id=validated_item["variant_id"],
                            quantity=validated_item["quantity"],
                            price_per_unit=validated_item["backend_price"],  # Use backend price
                            total_price=validated_item["backend_total"]     # Use backend total
                        )
                        self.db.add(order_item)
                        
                    except Exception as e:
                        # If stock decrement fails, rollback will happen automatically
                        logger.error(f"Stock decrement failed for variant {validated_item['variant_id']}: {e}")
                        raise HTTPException(
                            status_code=400,
                            detail=f"Stock unavailable for variant {validated_item['variant_id']}"
                        )

                # Process payment with backend-calculated amount and idempotency
                payment_service = PaymentService(self.db)
                payment_idempotency_key = f"payment_{order.id}_{idempotency_key}" if idempotency_key else None
                
                try:
                    payment_result = await payment_service.process_payment_idempotent(
                        user_id=user_id,
                        order_id=order.id,
                        amount=final_total["total_amount"],  # Use backend-calculated total
                        payment_method_id=request.payment_method_id,
                        idempotency_key=payment_idempotency_key,
                        request_id=str(uuid7())
                    )

                    if payment_result.get("status") != "succeeded":
                        # Payment failed - update order status and restore inventory
                        order.status = "payment_failed"
                        order.failure_reason = payment_result.get("error", "Payment processing failed")
                        
                        # Restore inventory for all items
                        for validated_item in validated_cart_items:
                            try:
                                await self.inventory_service.increment_stock_on_cancellation(
                                    variant_id=validated_item["variant_id"],
                                    quantity=validated_item["quantity"],
                                    location_id=None,  # Will be determined by service
                                    order_id=order.id,
                                    user_id=user_id
                                )
                            except Exception as restore_error:
                                logger.error(f"Failed to restore inventory for variant {validated_item['variant_id']}: {restore_error}")
                        
                        error_message = payment_result.get("error", "Payment processing failed")
                        raise HTTPException(status_code=400, detail=f"Payment failed: {error_message}")

                    # Payment succeeded - update order status
                    order.status = "confirmed"
                    order.version += 1  # Optimistic locking increment
                    
                except Exception as payment_error:
                    # Payment processing failed - update order and restore inventory
                    order.status = "payment_failed"
                    order.failure_reason = str(payment_error)
                    
                    # Restore inventory for all items
                    for validated_item in validated_cart_items:
                        try:
                            await self.inventory_service.increment_stock_on_cancellation(
                                variant_id=validated_item["variant_id"],
                                quantity=validated_item["quantity"],
                                location_id=None,
                                order_id=order.id,
                                user_id=user_id
                            )
                        except Exception as restore_error:
                            logger.error(f"Failed to restore inventory for variant {validated_item['variant_id']}: {restore_error}")
                    
                    raise

                # Create initial tracking event
                tracking_event = TrackingEvent(
                    order_id=order.id,
                    status="confirmed",
                    description="Order confirmed and payment processed",
                    location="Processing Center"
                )
                self.db.add(tracking_event)

                # Clear cart after successful order (validated cart)
                await cart_service.clear_cart(user_id=user_id)

                # Transaction will auto-commit here if no exceptions occurred
                
            # Refresh order after transaction commit
            await self.db.refresh(order)
            
            # POST-COMMIT VALIDATION: Verify order total is still correct after database commit
            post_commit_calculated_total = order.subtotal + order.shipping_cost + order.tax_amount - order.discount_amount
            
            # ALWAYS log post-commit state for debugging
            logger.info(f"🔍 POST-COMMIT CHECK - Order {order.id}:")
            logger.info(f"   Subtotal: ${order.subtotal:.2f}")
            logger.info(f"   Shipping: ${order.shipping_cost:.2f}")
            logger.info(f"   Tax:      ${order.tax_amount:.2f}")
            logger.info(f"   Discount: ${order.discount_amount:.2f}")
            logger.info(f"   Total:    ${order.total_amount:.2f}")
            logger.info(f"   Calculated: ${post_commit_calculated_total:.2f}")
            
            if abs(post_commit_calculated_total - order.total_amount) > 0.01:
                logger.error(f"❌ POST-COMMIT: Order total was modified after database commit for order {order.id}!")
                logger.error(f"  Expected: ${post_commit_calculated_total:.2f}")
                logger.error(f"  Actual:   ${order.total_amount:.2f}")
                logger.error(f"  Subtotal: ${order.subtotal:.2f}")
                logger.error(f"  Shipping: ${order.shipping_cost:.2f}")
                logger.error(f"  Tax:      ${order.tax_amount:.2f}")
                logger.error(f"  Discount: ${order.discount_amount:.2f}")
                logger.error(f"  Difference: ${abs(post_commit_calculated_total - order.total_amount):.2f}")
                
                # Write to debug file
                with open("/tmp/order_post_commit_errors.log", "a") as f:
                    f.write(f"{datetime.utcnow()}: POST-COMMIT ERROR\n")
                    f.write(f"  Order: {order.id}\n")
                    f.write(f"  Expected: ${post_commit_calculated_total:.2f}\n")
                    f.write(f"  Actual:   ${order.total_amount:.2f}\n")
                    f.write(f"  Difference: ${abs(post_commit_calculated_total - order.total_amount):.2f}\n\n")
                
                # This indicates a database trigger, constraint, or other process is modifying the order
                # For now, we'll fix it by updating the order with the correct total
                logger.warning(f"🛠️ Correcting order total from ${order.total_amount:.2f} to ${post_commit_calculated_total:.2f}")
                order.total_amount = post_commit_calculated_total
                await self.db.commit()
                await self.db.refresh(order)
                
                logger.info(f"✅ Order total corrected to ${order.total_amount:.2f}")
            else:
                logger.info(f"✅ Post-commit validation PASSED")
                # Write success to debug file
                with open("/tmp/order_post_commit_success.log", "a") as f:
                    f.write(f"{datetime.utcnow()}: POST-COMMIT SUCCESS\n")
                    f.write(f"  Order: {order.id}\n")
                    f.write(f"  Total: ${order.total_amount:.2f}\n\n")
            
            
            # Send ARQ events with idempotency after successful transaction commit
            try:
                await self._send_order_events_with_idempotency(order, user_id, validated_cart_items)
            except Exception as arq_error:
                # Log ARQ errors but don't fail the order
                logger.error(f"Failed to send order events for order {order.id}: {arq_error}")
                # Order is still successful even if events fail
                
        except HTTPException:
            # Re-raise HTTP exceptions (validation errors, payment failures, etc.)
            raise
        except Exception as e:
            # Any other exception during transaction will auto-rollback
            raise HTTPException(status_code=500, detail=f"Order processing failed: {str(e)}")

        return await self._format_order_response(order)

    async def get_user_orders(self, user_id: UUID, page: int = 1, limit: int = 10, status_filter: Optional[str] = None) -> Dict[str, Any]:
        """Get paginated list of user's orders"""
        try:
            query = select(Order).where(Order.user_id == user_id).options(
                selectinload(Order.items).selectinload(OrderItem.variant).selectinload(ProductVariant.images),
                selectinload(Order.items).selectinload(OrderItem.variant).selectinload(ProductVariant.product)
            )

            if status_filter:
                query = query.where(Order.status == status_filter)

            query = query.order_by(desc(Order.created_at))

            # Calculate offset
            offset = (page - 1) * limit

            # Get total count using COUNT() instead of loading all records
            from sqlalchemy import func
            count_query = select(func.count(Order.id)).where(Order.user_id == user_id)
            if status_filter:
                count_query = count_query.where(Order.status == status_filter)

            total_result = await self.db.execute(count_query)
            total = total_result.scalar() or 0

            # Get paginated results
            result = await self.db.execute(query.offset(offset).limit(limit))
            orders = result.scalars().all()

            formatted_orders = []
            for order in orders:
                formatted_orders.append(await self._format_order_response(order))

            return {
                "orders": formatted_orders,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            }
        except Exception as e:
            # Log the full error for debugging
            logger.error("Order retrieval failed", exception=e, metadata={
                "user_id": str(user_id),
                "operation": "get_user_orders",
                "critical": False
            })
            
            # Re-raise with more context
            from core.errors import APIException
            raise APIException(
                message=f"Failed to fetch orders: {str(e)}",
                metadata={
                    "user_id": str(user_id),
                    "page": page,
                    "limit": limit,
                    "status_filter": status_filter
                }
            )

    async def get_order_by_id(self, order_id: UUID, user_id: UUID) -> Optional[OrderResponse]:
        """Get a specific order by ID"""
        
        query = select(Order).where(and_(Order.id == order_id, Order.user_id == user_id)).options(
            selectinload(Order.items).selectinload(OrderItem.variant).selectinload(ProductVariant.images),
            selectinload(Order.items).selectinload(OrderItem.variant).selectinload(ProductVariant.product)
        )

        result = await self.db.execute(query)
        order = result.scalar_one_or_none()

        if not order:
            return None

        return await self._format_order_response(order)

    async def get_supplier_orders(self, supplier_id: UUID, page: int = 1, limit: int = 10, status_filter: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict[str, Any]:
        """Get paginated list of supplier's orders (orders containing supplier's products)"""
        
        # Query orders that contain items from this supplier's products
        query = select(Order).join(OrderItem).join(ProductVariant).join(Product).where(Product.supplier_id == supplier_id).options(
            selectinload(Order.items).selectinload(OrderItem.variant).selectinload(ProductVariant.images),
            selectinload(Order.items).selectinload(OrderItem.variant).selectinload(ProductVariant.product)
        ).distinct()

        if status_filter:
            query = query.where(Order.order_status == status_filter)

        if date_from:
            query = query.where(Order.created_at >= date_from)
        
        if date_to:
            query = query.where(Order.created_at <= date_to)

        query = query.order_by(desc(Order.created_at))

        # Calculate offset
        offset = (page - 1) * limit

        # Get total count
        count_query = select(func.count(Order.id)).join(OrderItem).join(ProductVariant).join(Product).where(Product.supplier_id == supplier_id).distinct()
        
        if status_filter:
            count_query = count_query.where(Order.order_status == status_filter)
        
        if date_from:
            count_query = count_query.where(Order.created_at >= date_from)
        
        if date_to:
            count_query = count_query.where(Order.created_at <= date_to)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Get paginated results
        result = await self.db.execute(query.offset(offset).limit(limit))
        orders = result.scalars().all()

        formatted_orders = []
        for order in orders:
            formatted_orders.append(await self._format_order_response(order))

        return {
            "orders": formatted_orders,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }

    async def cancel_order(self, order_id: UUID, user_id: UUID) -> OrderResponse:
        """Cancel an order with transaction safety"""
        query = select(Order).where(and_(Order.id == order_id, Order.user_id == user_id)).with_for_update()
        result = await self.db.execute(query)
        order = result.scalar_one_or_none()

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        if order.status not in ["pending", "confirmed"]:
            raise HTTPException(status_code=400, detail="Order cannot be cancelled")

        # Use transaction for order cancellation
        try:
            async with self.db.begin():
                order.status = "cancelled"

                # Increment stock for cancelled order items
                query_items = select(OrderItem).where(OrderItem.order_id == order.id).options(
                    selectinload(OrderItem.variant).selectinload(ProductVariant.inventory)
                )
                order_items_with_inventory = (await self.db.execute(query_items)).scalars().all()

                for item in order_items_with_inventory:
                    if not item.variant or not item.variant.inventory:
                        print(f"Warning: No inventory found for variant {item.variant_id} during order cancellation.")
                        continue
                    
                    # Use new increment stock method for cancellations
                    await self.inventory_service.increment_stock_on_cancellation(
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

                # Transaction will auto-commit here
                
            # Refresh order after transaction commit
            await self.db.refresh(order)

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Order cancellation failed: {str(e)}")

        return await self._format_order_response(order)

    async def update_order_status(
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
        
        if tracking_number:
            order.tracking_number = tracking_number
        if carrier_name:
            order.carrier_name = carrier_name

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
            from services.email import send_shipping_update_email, send_order_delivered_email
            
            # Get user details for email
            user_result = await self.db.execute(
                select(User).where(User.id == order.user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if user and user.email:
                if status == 'shipped':
                    # Send shipping update email
                    send_shipping_update_email(
                        background_tasks=background_tasks,
                        to_email=user.email,
                        customer_name=user.firstname or "Customer",
                        order_number=order.order_number or str(order.id)[:8],
                        tracking_number=order.tracking_number or "N/A",
                        carrier=order.carrier_name or order.carrier or "N/A",
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
                    
                    send_order_delivered_email(
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
            
            # Add to calculated subtotal
            calculated_subtotal += item.total_price or 0
            
            items.append(OrderItemResponse(
                id=str(item.id),
                variant_id=str(item.variant.id),
                quantity=item.quantity,
                price_per_unit=item.price_per_unit,
                total_price=item.total_price,
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
                logger.info(f"✅ Updated order {order.id} total in database to ${corrected_total:.2f}")
            except Exception as e:
                logger.error(f"Failed to update order total in database: {e}")
                # Continue with the corrected total even if DB update fails
        else:
            corrected_total = order.total_amount

        # Calculate estimated delivery
        estimated_delivery = None
        if order.status in ["confirmed", "shipped"]:
            estimated_days = 5  # Default, could be from shipping method
            estimated_delivery = (order.created_at + timedelta(days=estimated_days)).isoformat()

        return OrderResponse(
            id=str(order.id),
            user_id=str(order.user_id),
            status=order.status,
            total_amount=corrected_total,  # Use corrected total instead of order.total_amount
            subtotal=display_subtotal,
            tax_amount=order.tax_amount,
            shipping_amount=order.shipping_cost,
            discount_amount=order.discount_amount,  # Now using the actual field from Order model
            currency=order.currency,  # Use order's currency
            tracking_number=order.tracking_number,
            estimated_delivery=estimated_delivery,
            shipping_address=order.shipping_address,
            billing_address=order.billing_address,
            items=items,
            created_at=order.created_at.isoformat() if order.created_at else ""
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
                from core.logging import structured_logger
                structured_logger.warning(
                    message="Price discrepancies detected during checkout",
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
        shipping_address
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
                from services.shipping import ShippingService
                shipping_service = ShippingService(self.db)
                
                # Extract address info for shipping calculation
                address_dict = {
                    'country': shipping_address.get('country', 'US'),
                    'state': shipping_address.get('state'),
                    'city': shipping_address.get('city'),
                    'postal_code': shipping_address.get('postal_code')
                }
                
                shipping_cost = await shipping_service.calculate_shipping_cost(
                    cart_subtotal=subtotal,
                    address=address_dict,
                    shipping_method_id=shipping_method.id if hasattr(shipping_method, 'id') else None
                )
            
            # Calculate tax based on shipping address (tax applies to subtotal + shipping)
            tax_rate = await self._get_tax_rate(shipping_address)
            taxable_amount = subtotal + shipping_cost  # Tax applies to subtotal + shipping
            tax_amount = taxable_amount * tax_rate
            
            # Apply any discounts (from promocodes, etc.)
            discount_amount = await self._calculate_discount_amount(validated_items, subtotal)
            
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

    async def _calculate_discount_amount(self, cart_items: List, subtotal: float) -> float:
        """Calculate discount amount from applied promocodes"""
        try:
            discount_amount = 0.0
            
            # Check if any cart items have promocodes applied
            for item in cart_items:
                if hasattr(item, 'promocode') and item.promocode:
                    # Get promocode details
                    from models.promocode import Promocode
                    result = await self.db.execute(
                        select(Promocode).where(
                            and_(
                                Promocode.code == item.promocode,
                                Promocode.is_active == True,
                                Promocode.valid_from <= datetime.utcnow(),
                                Promocode.valid_until >= datetime.utcnow()
                            )
                        )
                    )
                    promocode = result.scalar_one_or_none()
                    
                    if promocode:
                        if promocode.discount_type == "percentage":
                            item_discount = (item.total_price * promocode.discount_value) / 100
                            # Apply maximum discount limit if set
                            if promocode.max_discount_amount:
                                item_discount = min(item_discount, promocode.max_discount_amount)
                            discount_amount += item_discount
                        elif promocode.discount_type == "fixed":
                            discount_amount += min(promocode.discount_value, item.total_price)
            
            # Apply cart-level promocodes (if any)
            # This would be implemented based on your cart structure
            
            return discount_amount
            
        except Exception as e:
            logger.error(f"Error calculating discount amount: {e}")
            return 0.0

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
                tax_rate_record = tax_rate_result.scalar_one_or_none()
                
                if tax_rate_record:
                    logger.info(f"Found state/province tax rate for {country}-{state}: {tax_rate_record.tax_rate} ({tax_rate_record.tax_name})")
                    return tax_rate_record.tax_rate
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
            tax_rate_record = tax_rate_result.scalar_one_or_none()
            
            if tax_rate_record:
                logger.info(f"Found country tax rate for {country}: {tax_rate_record.tax_rate} ({tax_rate_record.tax_name})")
                return tax_rate_record.tax_rate
            
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

    def _generate_cart_hash(self, cart: Cart, request: CheckoutRequest, request_id: Optional[str] = None) -> str:
        """
        Generate deterministic hash for cart contents and checkout details
        Used for idempotency key generation
        """
        # If request_id provided, use it for better idempotency
        if request_id:
            return f"req_{request_id}"
        
        # Fallback to cart-based hash for backward compatibility
        cart_items = sorted([
            f"{item.variant.id}:{item.quantity}:{item.price_per_unit}"
            for item in cart.items if not getattr(item, 'saved_for_later', False)
        ])
        
        cart_string = "|".join(cart_items)
        
        # Include checkout details
        checkout_details = f"{request.shipping_address_id}:{request.shipping_method_id}:{request.payment_method_id}"
        
        # Create hash
        full_string = f"{cart_string}|{checkout_details}"
        return hashlib.md5(full_string.encode()).hexdigest()[:16]

    async def _send_order_events_with_idempotency(self, order: Order, user_id: UUID, validated_cart_items: List[Dict[str, Any]]):
        """
        Send immutable ARQ events for order creation using new event system.
        Events are versioned, validated, and idempotent.
        """
        try:
            from core.arq_worker import enqueue_email, enqueue_notification
            
            # Use correlation ID for event tracing
            correlation_id = str(order.id)
            
            # Prepare order items for event
            order_items = []
            for item in validated_cart_items:
                order_items.append({
                    "product_id": item.get("product_id"),
                    "variant_id": item["variant_id"],
                    "quantity": item["quantity"],
                    "price_per_unit": float(item["backend_price"]),
                    "total_price": float(item["backend_total"]),
                    "product_name": item.get("product_name", "")
                })
            
            # Get shipping address for event
            shipping_address = {}
            if order.shipping_address:
                shipping_address = {
                    "street": order.shipping_address.street,
                    "city": order.shipping_address.city,
                    "state": order.shipping_address.state,
                    "country": order.shipping_address.country,
                    "postal_code": order.shipping_address.post_code
                }
            
            # Order created event handled by hybrid task system
            
            # Send order confirmation email using ARQ
            user_result = await self.db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            if user:
                await enqueue_email(
                    "order_confirmation",
                    user.email,
                    order_id=str(order.id),
                    order_details={
                        "items": order_items,
                        "total_amount": float(order.total_amount),
                        "currency": order.currency,
                        "shipping_address": shipping_address
                    }
                )
                
                # Send order notification
                await enqueue_notification(
                    str(user_id),
                    "order_created",
                    title="Order Confirmed",
                    message=f"Your order #{order.id} has been confirmed and is being processed.",
                    data={
                        "order_id": str(order.id),
                        "total_amount": float(order.total_amount),
                        "currency": order.currency
                    }
                )
            
            # Order payment event handled by hybrid task system
            
            logger.info(f"Successfully published order events for order {order.id} using new event system")
            
        except Exception as e:
            logger.error(f"Failed to publish order events using new event system: {e}")
            raise
    async def request_refund(
        self, 
        order_id: UUID, 
        user_id: UUID, 
        refund_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Request a refund for an order
        Delegates to the RefundService for comprehensive refund processing
        """
        try:
            from services.refunds import RefundService
            from schemas.refunds import RefundRequest
            
            # Create refund service
            refund_service = RefundService(self.db)
            
            # Convert refund_data to RefundRequest schema
            refund_request = RefundRequest(**refund_data)
            
            # Process refund request
            refund_response = await refund_service.request_refund(
                user_id=user_id,
                order_id=order_id,
                refund_request=refund_request
            )
            
            return refund_response.dict()
            
        except Exception as e:
            logger.error(f"Failed to request refund for order {order_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process refund request: {str(e)}"
            )
    def _generate_cart_hash(self, cart, request: CheckoutRequest) -> str:
        """Generate deterministic hash for cart state and checkout request"""
        import hashlib
        
        # Create hash from cart items and checkout details
        cart_data = {
            "items": [
                {
                    "variant_id": str(item.variant.id),
                    "quantity": item.quantity,
                    "price": float(item.price_per_unit)
                }
                for item in cart.items if not getattr(item, 'saved_for_later', False)
            ],
            "shipping_address_id": str(request.shipping_address_id),
            "shipping_method_id": str(request.shipping_method_id),
            "payment_method_id": str(request.payment_method_id)
        }
        
        # Sort items for consistent hashing
        cart_data["items"].sort(key=lambda x: x["variant_id"])
        
        # Create hash
        cart_str = str(cart_data)
        return hashlib.md5(cart_str.encode()).hexdigest()[:16]

    async def _convert_order_to_response(self, order: Order) -> OrderResponse:
        """Convert Order model to OrderResponse"""
        # Load order items if not already loaded
        if not hasattr(order, 'items') or not order.items:
            order_with_items = await self.db.execute(
                select(Order).where(Order.id == order.id).options(
                    selectinload(Order.items)
                )
            )
            order = await order_with_items.scalar_one()
        
        return OrderResponse(
            id=order.id,
            order_number=order.order_number,
            status=order.order_status,
            payment_status=order.payment_status,
            fulfillment_status=order.fulfillment_status,
            total_amount=order.total_amount,
            currency=order.currency,
            created_at=order.created_at,
            items=[
                OrderItemResponse(
                    id=item.id,
                    variant_id=item.variant_id,
                    quantity=item.quantity,
                    price_per_unit=item.price_per_unit,
                    total_price=item.total_price
                )
                for item in order.items
            ]
        )

    async def get_order_tracking(self, order_id: UUID, user_id: UUID) -> Dict[str, Any]:
        """Get order tracking information for authenticated user"""
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
                raise HTTPException(status_code=404, detail="Order not found")
            
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
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get order tracking for order {order_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve tracking information"
            )

    async def get_order_tracking_public(self, order_id: UUID) -> Dict[str, Any]:
        """Get order tracking information without authentication (public endpoint)"""
        try:
            # Get order with tracking events (no user_id filter for public access)
            query = select(Order).where(Order.id == order_id).options(
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
                    stock_check = await self.inventory_service.check_stock_availability(
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
            cart = await cart_service.get_or_create_cart(user_id)
            
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

    async def generate_invoice(self, order_id: UUID, user_id: UUID) -> Dict[str, Any]:
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
                # Model uses `shipping_cost` (renamed) — fall back if legacy attribute exists
                "shipping_amount": getattr(order, 'shipping_cost', getattr(order, 'shipping_amount', 0.0)),
                # discount_amount may be missing on the model for some records — default to 0.0
                "discount_amount": getattr(order, 'discount_amount', 0.0),
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
            logger.error(f"Failed to generate invoice for order {order_id}: {e}")
            logger.error(f"Order data: {order_data if 'order_data' in locals() else 'Not available'}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate invoice: {str(e)}"
            )

    async def add_order_note(self, order_id: UUID, user_id: UUID, note: str) -> Dict[str, Any]:
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

    async def get_order_notes(self, order_id: UUID, user_id: UUID) -> Dict[str, Any]:
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