"""
Comprehensive Cart Service with Backend-Only Pricing
PostgreSQL-based cart with real-time tax and pricing calculations
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_, func, update
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
from typing import Optional, Dict, Any, List
from uuid import UUID
from core.utils.uuid_utils import uuid7
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from core.logging import get_structured_logger

from models.cart import Cart, CartItem
from models.product import ProductVariant, Product
from models.user import User
from services.tax import TaxService
from core.config import settings

logger = get_structured_logger(__name__)


class CartValidationResult:
    """Result of cart validation with detailed information"""
    def __init__(
        self,
        valid: bool,
        can_checkout: bool,
        cart: Optional[Cart] = None,
        issues: List[Dict[str, Any]] = None,
        summary: Dict[str, Any] = None
    ):
        self.valid = valid
        self.can_checkout = can_checkout
        self.cart = cart
        self.issues = issues or []
        self.summary = summary or {}


class CartService:
    """
    Comprehensive PostgreSQL-based cart service with backend-only pricing
    All pricing calculations are performed server-side for security
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.tax_service = TaxService(db)

    async def get_cart_with_pricing(
        self, 
        user_id: Optional[UUID] = None,
        session_id: Optional[str] = None,
        country_code: str = 'US',
        province_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get cart with comprehensive pricing calculations
        All prices are calculated server-side from database
        """
        if not user_id:
            # Return empty cart for guests - they need to login to use cart
            return self._create_empty_cart_response(session_id, country_code, province_code)

        # Get or create cart for authenticated user
        cart = await self.get_or_create_cart(user_id)
        
        if not cart.items:
            return self._create_empty_cart_response(None, country_code, province_code, cart.id)

        # Calculate comprehensive pricing
        pricing_result = await self._calculate_cart_pricing(cart.items, country_code, province_code)
        
        # Build cart response with detailed pricing
        cart_response = {
            "id": str(cart.id),
            "user_id": str(cart.user_id),
            "items": [],
            "pricing": pricing_result,
            "subtotal": pricing_result['subtotal'],
            "tax_amount": pricing_result['tax_amount'],
            "shipping_amount": 0.0,  # Calculated at checkout
            "total_amount": pricing_result['subtotal'] + pricing_result['tax_amount'],
            "created_at": cart.created_at.isoformat() if cart.created_at else None,
            "updated_at": cart.updated_at.isoformat() if cart.updated_at else None,
            "country_code": country_code,
            "province_code": province_code,
            "item_count": len(cart.items),
            "currency": "USD"
        }
        
        # Add detailed item information
        for item in cart.items:
            try:
                # Check if variant and product are loaded
                if not item.variant:
                    logger.error(f"Cart item {item.id} has no variant loaded")
                    continue
                
                # Get current price (sale_price if available, otherwise base_price)
                current_price = item.variant.sale_price or item.variant.base_price
                if current_price is None:
                    logger.error(f"Variant {item.variant_id} has no price data")
                    current_price = Decimal('0.00')
                
                item_total = current_price * item.quantity
            
                cart_response["items"].append({
                    "id": str(item.id),
                    "variant_id": str(item.variant_id),
                    "product_id": str(item.product_id),
                    "quantity": item.quantity,
                    "unit_price": float(current_price),
                    "total_price": float(item_total),
                    "added_at": item.created_at.isoformat() if item.created_at else None,
                    "variant": {
                        "id": str(item.variant.id),
                        "name": item.variant.name,
                        "sku": item.variant.sku,
                        "base_price": float(item.variant.base_price),
                        "sale_price": float(item.variant.sale_price) if item.variant.sale_price else None,
                        "current_price": float(current_price),
                        "on_sale": item.variant.sale_price is not None,
                        "discount_percentage": (
                            round(((item.variant.base_price - item.variant.sale_price) / item.variant.base_price) * 100, 1)
                            if item.variant.sale_price else 0
                        ),
                        "weight": getattr(item.variant, 'weight', 0.0),  # Default weight if not available
                        "attributes": item.variant.attributes,
                        "is_active": item.variant.is_active,
                        "images": [
                            {
                                "id": str(img.id),
                                "url": img.url,
                                "alt_text": img.alt_text,
                                "is_primary": img.is_primary
                            } for img in item.variant.images
                        ] if item.variant.images else []
                    },
                    "product": {
                        "id": str(item.product.id),
                        "name": item.product.name,
                        "slug": item.product.slug,
                        "short_description": item.product.short_description,
                        "category_id": str(item.product.category_id),
                        "is_featured": item.product.is_featured,
                        "rating_average": item.product.rating_average,
                        "availability_status": item.product.availability_status
                    } if item.product else None
                })
            except Exception as e:
                logger.error(f"Error processing cart item {item.id}: {e}")
                continue
        
        return cart_response

    async def _calculate_cart_pricing(
        self, 
        cart_items: List[CartItem], 
        country_code: str, 
        province_code: Optional[str]
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive cart pricing with tax
        All calculations use current database prices
        """
        subtotal = Decimal('0.00')
        item_breakdown = []
        
        # Calculate subtotal from current variant prices
        for item in cart_items:
            try:
                # Check if variant is loaded
                if not item.variant:
                    logger.error(f"Cart item {item.id} has no variant loaded in pricing calculation")
                    continue
                
                # Always use current price from database (sale_price if available, otherwise base_price)
                current_price = Decimal(str(item.variant.sale_price or item.variant.base_price))
                if current_price is None:
                    logger.error(f"Variant {item.variant_id} has no price data in pricing calculation")
                    current_price = Decimal('0.00')
                
                item_total = current_price * Decimal(str(item.quantity))
                subtotal += item_total
                
                item_breakdown.append({
                    'variant_id': str(item.variant_id),
                    'quantity': item.quantity,
                    'unit_price': float(current_price),
                    'total_price': float(item_total),
                    'on_sale': item.variant.sale_price is not None
                })
            except Exception as e:
                logger.error(f"Error calculating price for cart item {item.id}: {e}")
                continue
        
        # Calculate tax based on location
        tax_amount = Decimal('0.00')
        tax_rate = 0.0
        if country_code and subtotal > 0:
            try:
                tax_rate = await self.tax_service.get_tax_rate(country_code, province_code)
                if tax_rate:
                    tax_amount = (subtotal * Decimal(str(tax_rate))).quantize(
                        Decimal('0.01'), rounding=ROUND_HALF_UP
                    )
                    logger.info(f"Tax calculated: {tax_rate * 100}% on ${subtotal} = ${tax_amount}")
            except Exception as e:
                logger.warning(f"Failed to calculate tax for {country_code}-{province_code}: {e}")
        
        return {
            'subtotal': float(subtotal),
            'tax_rate': tax_rate,
            'tax_amount': float(tax_amount),
            'item_count': len(cart_items),
            'items_breakdown': item_breakdown,
            'calculated_at': datetime.utcnow().isoformat(),
            'location': f"{country_code}-{province_code}" if province_code else country_code
        }

    async def validate_cart_comprehensive(
        self,
        user_id: UUID,
        country_code: str = 'US',
        province_code: Optional[str] = None
    ) -> CartValidationResult:
        """
        Comprehensive cart validation for checkout readiness
        Checks stock availability, pricing, and business rules
        """
        logger.info(f"Validating cart for user {user_id}")
        
        issues = []
        can_checkout = True
        
        # Get cart with full item details
        cart_result = await self.db.execute(
            select(Cart)
            .options(
                selectinload(Cart.items).selectinload(CartItem.variant).selectinload(ProductVariant.images),
                selectinload(Cart.items).selectinload(CartItem.variant).selectinload(ProductVariant.product),
                selectinload(Cart.items).selectinload(CartItem.variant).selectinload(ProductVariant.inventory),
                selectinload(Cart.items).selectinload(CartItem.product)
            )
            .where(Cart.user_id == user_id)
        )
        cart = cart_result.scalar_one_or_none()
        
        if not cart or not cart.items:
            return CartValidationResult(
                valid=False,
                can_checkout=False,
                issues=[{
                    'type': 'empty_cart',
                    'severity': 'error',
                    'message': 'Cart is empty'
                }]
            )
        
        # Validate each cart item
        valid_items = 0
        total_value = Decimal('0.00')
        
        for item in cart.items:
            item_issues = await self._validate_cart_item(item)
            issues.extend(item_issues)
            
            # Check if item has critical issues
            critical_issues = [i for i in item_issues if i.get('severity') == 'error']
            if not critical_issues:
                valid_items += 1
                current_price = item.variant.sale_price or item.variant.base_price
                total_value += Decimal(str(current_price)) * Decimal(str(item.quantity))
        
        # Check if we have any valid items
        if valid_items == 0:
            can_checkout = False
            issues.append({
                'type': 'no_valid_items',
                'severity': 'error',
                'message': 'No valid items in cart'
            })
        
        # Business rule validations
        if total_value < Decimal('1.00'):  # Minimum order value
            can_checkout = False
            issues.append({
                'type': 'minimum_order_value',
                'severity': 'error',
                'message': 'Order total must be at least $1.00'
            })
        
        # Calculate pricing for summary
        pricing = await self._calculate_cart_pricing(cart.items, country_code, province_code)
        
        summary = {
            'total_items': len(cart.items),
            'valid_items': valid_items,
            'invalid_items': len(cart.items) - valid_items,
            'subtotal': pricing['subtotal'],
            'tax_amount': pricing['tax_amount'],
            'estimated_total': pricing['subtotal'] + pricing['tax_amount'],
            'issues_count': len(issues),
            'error_count': len([i for i in issues if i.get('severity') == 'error']),
            'warning_count': len([i for i in issues if i.get('severity') == 'warning'])
        }
        
        is_valid = len([i for i in issues if i.get('severity') == 'error']) == 0
        
        logger.info(f"Cart validation completed: valid={is_valid}, can_checkout={can_checkout}")
        
        return CartValidationResult(
            valid=is_valid,
            can_checkout=can_checkout,
            cart=cart,
            issues=issues,
            summary=summary
        )

    async def _validate_cart_item(self, item: CartItem) -> List[Dict[str, Any]]:
        """Validate individual cart item"""
        issues = []
        
        try:
            # Check if variant is active
            if not item.variant or not item.variant.is_active:
                issues.append({
                    'type': 'inactive_variant',
                    'severity': 'error',
                    'message': f'Product variant "{item.variant.name if item.variant else "Unknown"}" is no longer available',
                    'variant_id': str(item.variant_id)
                })
                return issues
            
            # Check if product is active
            if item.product and item.product.product_status != 'active':
                issues.append({
                    'type': 'inactive_product',
                    'severity': 'error',
                    'message': f'Product "{item.product.name}" is no longer available',
                    'product_id': str(item.product_id)
                })
            
            # Check stock availability
            try:
                from services.inventory import InventoryService
                inventory_service = InventoryService(self.db)
                stock_check = await inventory_service.check_stock_availability(item.variant_id, item.quantity)
                
                if not stock_check.get('available', False):
                    severity = 'error' if stock_check.get('current_stock', 0) == 0 else 'warning'
                    issues.append({
                        'type': 'insufficient_stock',
                        'severity': severity,
                        'message': stock_check.get('message', f'Insufficient stock for "{item.variant.name}"'),
                        'variant_id': str(item.variant_id),
                        'requested_quantity': item.quantity,
                        'available_quantity': stock_check.get('current_stock', 0)
                    })
            except Exception as e:
                logger.warning(f"Could not check stock for variant {item.variant_id}: {e}")
                # Don't fail validation if stock check fails, just skip it
            
            # Check quantity limits
            if item.quantity <= 0:
                issues.append({
                    'type': 'invalid_quantity',
                    'severity': 'error',
                    'message': 'Quantity must be greater than 0',
                    'variant_id': str(item.variant_id)
                })
            elif item.quantity > 100:  # Business rule: max 100 per item
                issues.append({
                    'type': 'quantity_limit_exceeded',
                    'severity': 'warning',
                    'message': 'Quantity exceeds recommended limit of 100',
                    'variant_id': str(item.variant_id)
                })
        except Exception as e:
            logger.error(f"Error validating cart item {item.id}: {e}")
            issues.append({
                'type': 'validation_error',
                'severity': 'error',
                'message': 'Failed to validate cart item',
                'variant_id': str(item.variant_id)
            })
        
        return issues

    async def get_or_create_cart(self, user_id: UUID) -> Cart:
        """Get existing cart or create new one"""
        result = await self.db.execute(
            select(Cart)
            .options(
                selectinload(Cart.items).selectinload(CartItem.variant).selectinload(ProductVariant.images),
                selectinload(Cart.items).selectinload(CartItem.variant).selectinload(ProductVariant.product),
                selectinload(Cart.items).selectinload(CartItem.product)
            )
            .where(Cart.user_id == user_id)
        )
        cart = result.scalar_one_or_none()

        if not cart:
            # Create new cart
            cart = Cart(user_id=user_id)
            self.db.add(cart)
            await self.db.commit()
            await self.db.refresh(cart)

        return cart

    def _create_empty_cart_response(
        self, 
        session_id: Optional[str], 
        country_code: str, 
        province_code: Optional[str],
        cart_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Create empty cart response"""
        return {
            "id": str(cart_id) if cart_id else None,
            "user_id": None,
            "session_id": session_id,
            "items": [],
            "pricing": {
                "subtotal": 0.0,
                "tax_rate": 0.0,
                "tax_amount": 0.0,
                "item_count": 0,
                "items_breakdown": [],
                "calculated_at": datetime.utcnow().isoformat(),
                "location": f"{country_code}-{province_code}" if province_code else country_code
            },
            "subtotal": 0.0,
            "tax_amount": 0.0,
            "shipping_amount": 0.0,
            "total_amount": 0.0,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "country_code": country_code,
            "province_code": province_code,
            "item_count": 0,
            "currency": "USD"
        }

    # Legacy method for backward compatibility
    async def get_cart(self, *args, **kwargs):
        """Legacy method - redirects to get_cart_with_pricing"""
        return await self.get_cart_with_pricing(*args, **kwargs)
    
    # Legacy method for backward compatibility  
    async def validate_cart(self, user_id: UUID, **kwargs):
        """Legacy method - redirects to validate_cart_comprehensive"""
        result = await self.validate_cart_comprehensive(user_id, **kwargs)
        return {
            'valid': result.valid,
            'can_checkout': result.can_checkout,
            'cart': result.cart,
            'issues': result.issues,
            'summary': result.summary
        }

        # Enrich cart items with detailed variant data
        for item in cart.items:
            variant = item.variant
            product = item.product or variant.product if variant else None
            
            item_data = {
                "id": item.id,
                "cart_id": item.cart_id,
                "variant_id": item.variant_id,
                "quantity": item.quantity,
                "price_per_unit": float(item.price_per_unit),
                "total_price": float(item.total_price),
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None
            }

            # Add comprehensive variant data if available
            if variant:
                # Calculate discount information
                discount_percentage = 0
                if variant.sale_price and variant.sale_price < variant.base_price:
                    discount_percentage = round(((variant.base_price - variant.sale_price) / variant.base_price) * 100, 2)
                
                variant_dict = {
                    'id': variant.id,
                    'product_id': variant.product_id,
                    'sku': variant.sku,
                    'name': variant.name,
                    'base_price': float(variant.base_price),
                    'sale_price': float(variant.sale_price) if variant.sale_price else None,
                    'current_price': float(variant.sale_price or variant.base_price),
                    'discount_percentage': discount_percentage,
                    'stock': variant.stock,
                    'is_active': variant.is_active,
                    'attributes': variant.attributes or {},
                    'barcode': variant.barcode,
                    'qr_code': variant.qr_code,
                    'created_at': variant.created_at.isoformat() if variant.created_at else None,
                    'updated_at': variant.updated_at.isoformat() if variant.updated_at else None,
                    'images': [],
                    'primary_image': None,
                    'image_count': len(variant.images) if variant.images else 0
                }
                
                # Add detailed product information
                if product:
                    variant_dict.update({
                        'product_name': product.name,
                        'product_description': product.description,
                        'product_short_description': product.short_description,
                        'product_slug': product.slug,
                        'product_category_id': str(product.category_id),
                        'product_rating_average': product.rating_average,
                        'product_rating_count': product.rating_count,
                        'product_is_featured': product.is_featured,
                        'product_specifications': product.specifications,
                        'product_dietary_tags': product.dietary_tags,
                        'product_tags': product.tags.split(",") if product.tags else [],
                        'product_origin': product.origin
                    })
                
                # Process images with detailed information
                if variant.images:
                    # Sort images by sort_order, then by is_primary (primary first)
                    sorted_images = sorted(variant.images, key=lambda x: (not x.is_primary, x.sort_order))
                    
                    variant_dict['images'] = [
                        {
                            'id': img.id,
                            'variant_id': img.variant_id,
                            'url': img.url,
                            'alt_text': img.alt_text or f"{variant.name} - Image {img.sort_order + 1}",
                            'is_primary': img.is_primary,
                            'sort_order': img.sort_order,
                            'format': img.format,
                            'created_at': img.created_at.isoformat() if img.created_at else None
                        }
                        for img in sorted_images
                    ]
                    
                    # Set primary image (first primary image or first image)
                    primary_img = next((img for img in sorted_images if img.is_primary), sorted_images[0] if sorted_images else None)
                    if primary_img:
                        variant_dict['primary_image'] = {
                            'id': primary_img.id,
                            'variant_id': primary_img.variant_id,
                            'url': primary_img.url,
                            'alt_text': primary_img.alt_text or f"{variant.name} - Primary Image",
                            'is_primary': primary_img.is_primary,
                            'sort_order': primary_img.sort_order,
                            'format': primary_img.format,
                            'created_at': primary_img.created_at.isoformat() if primary_img.created_at else None
                        }
                else:
                    # Provide fallback image information
                    variant_dict['images'] = []
                    variant_dict['primary_image'] = {
                        'id': None,
                        'variant_id': variant.id,
                        'url': '/placeholder-product.jpg',  # Fallback image
                        'alt_text': f"{variant.name} - No Image Available",
                        'is_primary': True,
                        'sort_order': 0,
                        'format': 'jpg',
                        'created_at': None
                    }
                
                # Add inventory information
                if hasattr(variant, 'inventory') and variant.inventory:
                    variant_dict.update({
                        'inventory_quantity_available': variant.inventory.quantity_available,
                        'inventory_reorder_level': variant.inventory.reorder_point,
                        'inventory_last_updated': variant.inventory.updated_at.isoformat() if variant.inventory.updated_at else None
                    })
                
                item_data['variant'] = variant_dict

            cart_data['items'].append(item_data)

        return cart_data

    async def add_to_cart(
        self,
        user_id: Optional[UUID] = None,
        variant_id: UUID = None,
        quantity: int = 1,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add item to cart in PostgreSQL"""
        
        if not user_id:
            raise HTTPException(status_code=401, detail="User must be authenticated to add items to cart")

        # Get variant to check availability and get current price
        result = await self.db.execute(
            select(ProductVariant)
            .options(selectinload(ProductVariant.product))
            .where(ProductVariant.id == variant_id)
        )
        variant = result.scalar_one_or_none()
        
        if not variant:
            raise HTTPException(status_code=404, detail="Product variant not found")
        
        if not variant.is_active:
            raise HTTPException(status_code=400, detail="Product variant is not available")
        
        if variant.stock < quantity:
            raise HTTPException(
                status_code=400, 
                detail=f"Insufficient stock. Only {variant.stock} items available"
            )

        # Get or create cart
        result = await self.db.execute(
            select(Cart).where(Cart.user_id == user_id)
        )
        cart = result.scalar_one_or_none()
        
        if not cart:
            cart = Cart(user_id=user_id)
            self.db.add(cart)
            await self.db.flush()  # Get the cart ID

        # Check if item already exists in cart
        result = await self.db.execute(
            select(CartItem).where(
                and_(
                    CartItem.cart_id == cart.id,
                    CartItem.variant_id == variant_id
                )
            )
        )
        existing_item = result.scalar_one_or_none()

        if existing_item:
            # Update existing item
            new_quantity = existing_item.quantity + quantity
            if variant.stock < new_quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot add {quantity} more items. Only {variant.stock - existing_item.quantity} more available"
                )
            
            existing_item.quantity = new_quantity
            existing_item.price_per_unit = variant.sale_price or variant.base_price
        else:
            # Add new item
            new_item = CartItem(
                id=uuid7(),
                cart_id=cart.id,
                product_id=variant.product_id,
                variant_id=variant_id,
                quantity=quantity,
                price_per_unit=variant.sale_price or variant.base_price
            )
            self.db.add(new_item)

        await self.db.commit()
        
        # Return updated cart
        return await self.get_cart(user_id=user_id)

    async def update_cart_item_quantity(
        self,
        user_id: Optional[UUID] = None,
        cart_item_id: UUID = None,
        quantity: int = 1,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update cart item quantity"""
        if not user_id:
            raise HTTPException(status_code=401, detail="User must be authenticated")

        # Get cart item
        result = await self.db.execute(
            select(CartItem)
            .options(selectinload(CartItem.variant))
            .join(Cart)
            .where(
                and_(
                    CartItem.id == cart_item_id,
                    Cart.user_id == user_id
                )
            )
        )
        cart_item = result.scalar_one_or_none()
        
        if not cart_item:
            raise HTTPException(status_code=404, detail="Cart item not found")

        # Check stock availability
        variant = cart_item.variant
        if not variant:
            raise HTTPException(status_code=404, detail="Product variant not found")
        
        if variant.stock < quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock. Only {variant.stock} items available"
            )

        # Update item
        cart_item.quantity = quantity
        cart_item.price_per_unit = variant.sale_price or variant.base_price
        
        await self.db.commit()
        
        # Return updated cart
        return await self.get_cart(user_id=user_id)

    async def remove_from_cart_by_item_id(
        self,
        user_id: Optional[UUID] = None,
        cart_item_id: UUID = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Remove item from cart by item ID"""
        
        if not user_id:
            raise HTTPException(status_code=401, detail="User must be authenticated")

        # Delete cart item
        result = await self.db.execute(
            delete(CartItem)
            .where(
                and_(
                    CartItem.id == cart_item_id,
                    CartItem.cart_id.in_(
                        select(Cart.id).where(Cart.user_id == user_id)
                    )
                )
            )
        )
        
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Cart item not found")

        await self.db.commit()
        
        # Return updated cart
        return await self.get_cart(user_id=user_id)

    async def clear_cart(
        self,
        user_id: Optional[UUID] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Clear all items from cart"""
        
        if not user_id:
            raise HTTPException(status_code=401, detail="User must be authenticated")

        # Delete all cart items for user
        await self.db.execute(
            delete(CartItem)
            .where(
                CartItem.cart_id.in_(
                    select(Cart.id).where(Cart.user_id == user_id)
                )
            )
        )
        
        await self.db.commit()
        
        # Return empty cart
        return await self.get_cart(user_id=user_id)

    async def get_cart_item_count(
        self,
        user_id: Optional[UUID] = None,
        session_id: Optional[str] = None
    ) -> int:
        """Get total number of items in cart"""
        
        if not user_id:
            return 0

        result = await self.db.execute(
            select(func.coalesce(func.sum(CartItem.quantity), 0))
            .select_from(CartItem)
            .join(Cart)
            .where(Cart.user_id == user_id)
        )
        
        return result.scalar() or 0

    async def merge_guest_cart(
        self,
        user_id: UUID,
        guest_cart_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge guest cart with user cart after login
        Since PostgreSQL version doesn't support guest carts,
        this is mainly for compatibility
        """
        # For PostgreSQL version, just return the user's existing cart
        return await self.get_cart(user_id=user_id)

    async def get_checkout_summary(
        self,
        user_id: Optional[UUID] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get cart summary for checkout"""
        
        cart_data = await self.get_cart(user_id=user_id, session_id=session_id)
        
        # Add checkout-specific information
        checkout_summary = {
            **cart_data,
            "can_checkout": len(cart_data["items"]) > 0 and cart_data["total_amount"] > 0,
            "checkout_url": "/checkout",
            "estimated_delivery": "3-5 business days"  # Can be made dynamic
        }
        
        return checkout_summary

    async def apply_promocode(
        self,
        user_id: Optional[UUID] = None,
        code: str = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Apply promocode to cart (placeholder implementation)"""
        # This would integrate with a promocode service
        # For now, return cart without changes
        cart_data = await self.get_cart(user_id=user_id, session_id=session_id)
        return {
            **cart_data,
            "promocode_applied": False,
            "message": "Promocode functionality not yet implemented"
        }

    async def remove_promocode(
        self,
        user_id: Optional[UUID] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Remove promocode from cart (placeholder implementation)"""
        # This would integrate with a promocode service
        # For now, return cart without changes
        cart_data = await self.get_cart(user_id=user_id, session_id=session_id)
        return {
            **cart_data,
            "promocode_removed": True,
            "message": "Promocode removed"
        }

    async def get_shipping_options(
        self,
        user_id: Optional[UUID] = None,
        address: Dict[str, Any] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get shipping options for cart from database"""
        from models.shipping import ShippingMethod
        from sqlalchemy import select
        
        try:
            # Get active shipping methods from database
            result = await self.db.execute(
                select(ShippingMethod).where(ShippingMethod.is_active == True)
            )
            shipping_methods = result.scalars().all()
            
            # Convert to API format
            shipping_options = []
            for method in shipping_methods:
                shipping_options.append({
                    "id": str(method.id),  # Convert UUID to string for JSON serialization
                    "name": method.name,
                    "description": method.description or f"{method.estimated_days} business days",
                    "price": method.price,
                    "estimated_days": str(method.estimated_days)
                })
            
            # If no shipping methods in database, return default options
            if not shipping_options:
                shipping_options = [
                    {
                        "id": "standard",
                        "name": "Standard Shipping",
                        "description": "3-5 business days",
                        "price": 5.99,
                        "estimated_days": "3-5"
                    },
                    {
                        "id": "express",
                        "name": "Express Shipping", 
                        "description": "1-2 business days",
                        "price": 12.99,
                        "estimated_days": "1-2"
                    }
                ]
            
            return {
                "shipping_options": shipping_options
            }
            
        except Exception as e:
            # Fallback to default options if database query fails
            return {
                "shipping_options": [
                    {
                        "id": "standard",
                        "name": "Standard Shipping",
                        "description": "3-5 business days",
                        "price": 5.99,
                        "estimated_days": "3-5"
                    },
                    {
                        "id": "express",
                        "name": "Express Shipping",
                        "description": "1-2 business days", 
                        "price": 12.99,
                        "estimated_days": "1-2"
                    }
                ]
            }

    async def calculate_totals(
        self,
        user_id: Optional[UUID] = None,
        data: Dict[str, Any] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Calculate cart totals with shipping and tax"""
        cart_data = await self.get_cart(user_id=user_id, session_id=session_id)
        
        # Extract shipping method from data
        shipping_cost = 0.0
        if data and "shipping_method_id" in data:
            shipping_options = await self.get_shipping_options(user_id, session_id=session_id)
            for option in shipping_options.get("shipping_options", []):
                if option["id"] == data["shipping_method_id"]:
                    shipping_cost = option["price"]
                    break
        
        # Recalculate totals
        subtotal = cart_data["subtotal"]
        tax_amount = cart_data["tax_amount"]
        total_amount = subtotal + tax_amount + shipping_cost
        
        return {
            **cart_data,
            "shipping_amount": shipping_cost,
            "total_amount": total_amount,
            "calculation_timestamp": datetime.utcnow().isoformat()
        }

    async def merge_carts(
        self,
        user_id: UUID,
        session_id: str
    ) -> Dict[str, Any]:
        """Merge guest cart with user cart after login"""
        # For PostgreSQL version, just return the user's existing cart
        # since we don't support guest carts in this implementation
        return await self.get_cart(user_id=user_id)