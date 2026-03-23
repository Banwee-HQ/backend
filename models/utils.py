"""
Utility functions for model operations and lazy loading
"""

from typing import List, Optional, TypeVar, Dict, Any
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .user import User
from .product import Product, ProductVariant
from .cart import Cart, CartItem
from .order import Order, OrderItem
from .review import Review
from .wishlist import Wishlist, WishlistItem

T = TypeVar('T')


class ModelLoader:
    """Utility class for loading models with proper relationships"""

    @staticmethod
    async def load_user_with_relations(
        session: AsyncSession,
        user_id: int,
        include_addresses: bool = False,
        include_orders: bool = False,
        include_wishlists: bool = False,
        include_payment_methods: bool = False
    ) -> Optional[User]:
        """Load user with specified relationships"""
        query = select(User).where(User.id == user_id)

        if include_addresses:
            query = query.options(selectinload(User.addresses))
        if include_orders:
            query = query.options(selectinload(User.orders))
        if include_wishlists:
            query = query.options(selectinload(User.wishlists))
        if include_payment_methods:
            query = query.options(selectinload(User.payment_methods))

        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def load_product_with_relations(
        session: AsyncSession,
        product_id: int,
        include_variants: bool = True,
        include_images: bool = True,
        include_category: bool = True,
        include_supplier: bool = False,
        include_reviews: bool = False
    ) -> Optional[Product]:
        """Load product with specified relationships"""
        query = select(Product).where(Product.id == product_id)

        if include_category:
            query = query.options(selectinload(Product.category))
        if include_supplier:
            query = query.options(selectinload(Product.supplier))
        if include_variants:
            if include_images:
                query = query.options(
                    selectinload(Product.variants).selectinload(
                        ProductVariant.images)
                )
            else:
                query = query.options(selectinload(Product.variants))
        if include_reviews:
            query = query.options(
                selectinload(Product.reviews).selectinload(Review.user)
            )

        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def load_products_with_relations(
        session: AsyncSession,
        limit: int = 20,
        offset: int = 0,
        include_variants: bool = True,
        include_primary_image: bool = True,
        include_category: bool = True,
        category_id: Optional[int] = None,
        featured_only: bool = False
    ) -> List[Product]:
        """Load multiple products with relationships"""
        query = select(Product).where(Product.is_active == True)

        if category_id:
            query = query.where(Product.category_id == category_id)
        if featured_only:
            query = query.where(Product.featured == True)

        if include_category:
            query = query.options(selectinload(Product.category))

        if include_variants:
            if include_primary_image:
                query = query.options(
                    selectinload(Product.variants).selectinload(
                        ProductVariant.images)
                )
            else:
                query = query.options(selectinload(Product.variants))

        query = query.limit(limit).offset(offset)
        result = await session.execute(query)
        return result.scalars().all()

    @staticmethod
    async def load_cart_with_items(
        session: AsyncSession,
        user_id: int
    ) -> Optional[Cart]:
        """Load cart with items and variant details"""
        query = select(Cart).where(Cart.user_id == user_id).options(
            selectinload(Cart.items).selectinload(
                CartItem.variant).selectinload(ProductVariant.product),
            selectinload(Cart.items).selectinload(
                CartItem.variant).selectinload(ProductVariant.images)
        )

        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def load_order_with_details(
        session: AsyncSession,
        order_id: str,
        include_tracking: bool = True
    ) -> Optional[Order]:
        """Load order with full details"""
        query = select(Order).where(Order.id == order_id).options(
            selectinload(Order.items).selectinload(
                OrderItem.variant).selectinload(ProductVariant.product),
            selectinload(Order.user)
        )

        if include_tracking:
            query = query.options(selectinload(Order.tracking_events))

        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def load_wishlist_with_items(
        session: AsyncSession,
        wishlist_id: int
    ) -> Optional[Wishlist]:
        """Load wishlist with product details"""
        query = select(Wishlist).where(Wishlist.id == wishlist_id).options(
            selectinload(Wishlist.items).selectinload(WishlistItem.product).selectinload(
                Product.variants).selectinload(ProductVariant.images)
        )

        result = await session.execute(query)
        return result.scalar_one_or_none()


class ModelSerializer:
    """Utility class for serializing models to dictionaries"""

    @staticmethod
    def serialize_user(user: User, include_relations: bool = False) -> Dict[str, Any]:
        """Serialize user to dictionary"""
        data = user.to_dict()

        if include_relations:
            if hasattr(user, 'addresses') and user.addresses:
                data['addresses'] = [addr.to_dict() for addr in user.addresses]
            if hasattr(user, 'payment_methods') and user.payment_methods:
                data['payment_methods'] = [pm.to_dict()
                                           for pm in user.payment_methods]

        return data

    @staticmethod
    def serialize_product(product: Product, include_relations: bool = True) -> Dict[str, Any]:
        """Serialize product to dictionary"""
        data = product.to_dict()

        if include_relations:
            if hasattr(product, 'category') and product.category:
                data['category'] = {
                    'id': product.category.id,
                    'name': product.category.name,
                    'image_url': product.category.image_url
                }
            if hasattr(product, 'supplier') and product.supplier:
                data['supplier'] = {
                    'id': product.supplier.id,
                    'firstname': product.supplier.firstname,
                    'lastname': product.supplier.lastname,
                    'full_name': product.supplier.full_name
                }
            if hasattr(product, 'variants') and product.variants:
                data['variants'] = [variant.to_dict()
                                    for variant in product.variants]

        return data

    @staticmethod
    def serialize_cart(cart: Cart) -> Dict[str, Any]:
        """Serialize cart to dictionary"""
        items_data = []
        total_amount = 0
        total_items = 0

        for item in cart.items:
            item_data = {
                'id': item.id,
                'variant_id': item.variant_id,
                'quantity': item.quantity,
                'price_per_unit': item.price_per_unit,
                'total_price': item.price_per_unit * item.quantity,
                'variant': item.variant.to_dict() if item.variant else None
            }
            items_data.append(item_data)
            total_amount += item_data['total_price']
            total_items += item.quantity

        return {
            'id': cart.id,
            'user_id': cart.user_id,
            'items': items_data,
            'total_items': total_items,
            'total_amount': total_amount,
            'created_at': cart.created_at.isoformat() if cart.created_at else None,
            'updated_at': cart.updated_at.isoformat() if cart.updated_at else None,
        }

    @staticmethod
    def serialize_order(order: Order, include_items: bool = True) -> Dict[str, Any]:
        """Serialize order to dictionary"""
        data = {
            'id': str(order.id),
            'user_id': order.user_id,
            'status': order.status,
            'total_amount': order.total_amount,
            'shipping_address_id': order.shipping_address_id,
            'shipping_method_id': order.shipping_method_id,
            'payment_method_id': order.payment_method_id,
            'promocode_id': order.promocode_id,
            'carrier_name': order.carrier_name,
            'tracking_number': order.tracking_number,
            'notes': order.notes,
            'created_at': order.created_at.isoformat() if order.created_at else None,
            'updated_at': order.updated_at.isoformat() if order.updated_at else None,
        }

        if include_items and hasattr(order, 'items') and order.items:
            data['items'] = []
            for item in order.items:
                item_data = {
                    'id': item.id,
                    'variant_id': item.variant_id,
                    'quantity': item.quantity,
                    'price_per_unit': item.price_per_unit,
                    'total_price': item.total_price,
                }
                if hasattr(item, 'variant') and item.variant:
                    item_data['variant'] = item.variant.to_dict()
                data['items'].append(item_data)

        if hasattr(order, 'tracking_events') and order.tracking_events:
            data['tracking_events'] = [
                {
                    'id': event.id,
                    'status': event.status,
                    'description': event.description,
                    'location': event.location,
                    'timestamp': event.timestamp.isoformat() if event.timestamp else None,
                }
                for event in order.tracking_events
            ]

        return data


# Utility functions for common queries
async def get_user_cart_count(session: AsyncSession, user_id: int) -> int:
    """Get total items in user's cart"""
    query = select(Cart).where(Cart.user_id == user_id).options(
        selectinload(Cart.items)
    )
    result = await session.execute(query)
    cart = result.scalar_one_or_none()

    if not cart:
        return 0

    return sum(item.quantity for item in cart.items)


async def get_user_wishlist_count(session: AsyncSession, user_id: int) -> int:
    """Get total items in user's wishlists"""
    query = select(Wishlist).where(Wishlist.user_id == user_id).options(
        selectinload(Wishlist.items)
    )
    result = await session.execute(query)
    wishlists = result.scalars().all()

    return sum(len(wishlist.items) for wishlist in wishlists)


async def get_product_average_rating(session: AsyncSession, product_id: int) -> float:
    """Calculate average rating for a product"""
    query = select(Review).where(
        Review.product_id == product_id,
        Review.is_approved == True
    )
    result = await session.execute(query)
    reviews = result.scalars().all()

    if not reviews:
        return 0.0

    return sum(review.rating for review in reviews) / len(reviews)
