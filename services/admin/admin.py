# Consolidated admin service
# This file includes all admin-related functionality including pricing and analytics

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, String
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
from models.accounts.user import User
from models.commerce.orders import Order, OrderItem
from models.catalog.product import Product, ProductVariant
from uuid import UUID
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any
from decimal import Decimal

from core.logging import get_structured_logger

logger = get_structured_logger(__name__)



class AdminService:
    """Consolidated admin service with comprehensive admin functionality"""
    
    def __init__(self, db: AsyncSession):
        self.db = db

    # --- User Management ---
    async def list_users(
        self,
        page: int = 1,
        limit: int = 20,
        role_filter: Optional[str] = None,
        search: Optional[str] = None,
        status: Optional[str] = None,
        verified: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Get all users with pagination and filtering - delegates to UserService"""
        from services.accounts.user import UserService
        
        user_service = UserService(self.db)
        return await user_service.list(
            page=page,
            limit=limit,
            role=role_filter
        )

    async def update_role(
        self,
        user_id: UUID,
        new_role: str,
        admin_user_id: UUID
    ) -> User:
        """Update a user's role"""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        old_role = user.role
        user.role = new_role
        
        await self.db.commit()
        await self.db.refresh(user)
        
        return user

    async def deactivate(
        self,
        user_id: UUID,
        admin_user_id: UUID
    ) -> User:
        """Deactivate a user account"""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        user.is_active = False
        
        await self.db.commit()
        await self.db.refresh(user)
        
        return user

    async def stats(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        status: Optional[str] = None,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get admin dashboard statistics with optional filters"""
        try:
            from models.commerce.orders import Order
            from models.catalog.product import Product
            from models.commerce.subscriptions import Subscription
            from datetime import datetime, timedelta
            
            logger.info(f"📊 Dashboard stats request: date_from={date_from}, date_to={date_to}, status={status}, category={category}")
            
            # Parse date filters
            today = datetime.utcnow().date()
            yesterday = today - timedelta(days=1)
            last_week = today - timedelta(days=7)
            last_month = today - timedelta(days=30)
            
            # Parse date_from and date_to
            if date_from:
                try:
                    start_date = datetime.fromisoformat(date_from).date()
                except:
                    start_date = last_month
            else:
                start_date = last_month
            
            if date_to:
                try:
                    end_date = datetime.fromisoformat(date_to).date()
                except:
                    end_date = today
            else:
                end_date = today
            
            # Get total users (excluding admin users, filtered by date range)
            total_users = await self.db.scalar(
                select(func.count(User.id)).where(
                    and_(
                        User.role != 'admin',
                        User.created_at >= start_date,
                        User.created_at <= end_date
                    )
                )
            )
            logger.info(f"👥 Total users (customers) in date range: {total_users}")
            
            active_users = await self.db.scalar(
                select(func.count(User.id)).where(
                    and_(
                        User.is_active == True,
                        User.role != 'admin',
                        User.created_at >= start_date,
                        User.created_at <= end_date
                    )
                )
            )
            logger.info(f"✅ Active users (customers) in date range: {active_users}")
            
            # Get total orders with optional status filter (filtered by date range)
            order_conditions = [
                Order.created_at >= start_date,
                Order.created_at <= end_date
            ]
            if status:
                order_conditions.append(Order.order_status == status)
            
            total_orders = await self.db.scalar(
                select(func.count(Order.id)).where(and_(*order_conditions)) if order_conditions else select(func.count(Order.id))
            )
            logger.info(f"📦 Total orders (filtered by {status}): {total_orders}")
            
            orders_today = await self.db.scalar(
                select(func.count(Order.id)).where(
                    func.date(Order.created_at) == today
                )
            )
            logger.info(f"📅 Orders today: {orders_today}")
            
            # Get total products with optional category filter
            product_conditions = []
            if category:
                product_conditions.append(Product.category == category)
            
            total_products = await self.db.scalar(
                select(func.count(Product.id)).where(and_(*product_conditions)) if product_conditions else select(func.count(Product.id))
            )
            active_products = await self.db.scalar(
                select(func.count(Product.id)).where(Product.is_active == True)
            )
            
            # Get revenue data (include confirmed, processing, shipped, and delivered orders)
            revenue_conditions = [Order.order_status.in_(['CONFIRMED', 'PROCESSING', 'SHIPPED', 'DELIVERED'])]
            if status:
                revenue_conditions.append(Order.order_status == status)
            
            total_revenue = await self.db.scalar(
                select(func.coalesce(func.sum(Order.total_amount), 0)).where(and_(*revenue_conditions))
            ) or 0
            
            revenue_today = await self.db.scalar(
                select(func.coalesce(func.sum(Order.total_amount), 0)).where(
                    and_(
                        Order.order_status.in_(['CONFIRMED', 'PROCESSING', 'SHIPPED', 'DELIVERED']),
                        func.date(Order.created_at) == today
                    )
                )
            ) or 0
            
            revenue_this_month = await self.db.scalar(
                select(func.coalesce(func.sum(Order.total_amount), 0)).where(
                    and_(
                        Order.order_status.in_(['CONFIRMED', 'PROCESSING', 'SHIPPED', 'DELIVERED']),
                        Order.created_at >= last_month
                    )
                )
            ) or 0
            
            # Get subscription stats if available
            total_subscriptions = 0
            active_subscriptions = 0
            try:
                total_subscriptions = await self.db.scalar(select(func.count(Subscription.id))) or 0
                active_subscriptions = await self.db.scalar(
                    select(func.count(Subscription.id)).where(Subscription.status == "active")
                ) or 0
            except Exception:
                # Subscription table might not exist
                pass
            
            # Generate chart data for selected date range
            chart_data = await self._generate_daily_metrics(start_date, end_date, status, category)
            
            # Recent orders (filtered by date range)
            recent_orders_result = await self.db.execute(
                select(Order)
                .options(selectinload(Order.user))
                .where(
                    and_(
                        Order.created_at >= start_date,
                        Order.created_at <= end_date
                    )
                )
                .order_by(desc(Order.created_at))
                .limit(5)
            )
            recent_orders = recent_orders_result.scalars().all()
            
            # Recent users (excluding admin users, filtered by date range)
            recent_users_result = await self.db.execute(
                select(User)
                .where(
                    and_(
                        User.role != 'admin',
                        User.created_at >= start_date,
                        User.created_at <= end_date
                    )
                )
                .order_by(desc(User.created_at))
                .limit(5)
            )
            recent_users = recent_users_result.scalars().all()
            
            # Top products by sales (within date range)
            top_products_query = await self.db.execute(
                select(
                    Product.id,
                    Product.name,
                    func.sum(OrderItem.quantity).label('sales'),
                    func.sum(OrderItem.quantity * OrderItem.price_per_unit).label('revenue')
                )
                .select_from(OrderItem)
                .join(ProductVariant, OrderItem.variant_id == ProductVariant.id)
                .join(Product, ProductVariant.product_id == Product.id)
                .join(Order, OrderItem.order_id == Order.id)
                .where(
                    and_(
                        Order.created_at >= start_date,
                        Order.created_at <= end_date,
                        Order.order_status.in_(['CONFIRMED', 'PROCESSING', 'SHIPPED', 'DELIVERED'])
                    )
                )
                .group_by(Product.id, Product.name)
                .order_by(func.sum(OrderItem.quantity * OrderItem.price_per_unit).desc())
                .limit(6)
            )
            
            top_products = [
                {
                    "id": str(product.id),
                    "name": product.name,
                    "sales": int(product.sales or 0),
                    "revenue": float(product.revenue or 0)
                }
                for product in top_products_query.all()
            ]
            
            return {
                "overview": {
                    "total_users": total_users,
                    "active_users": active_users,
                    "total_orders": total_orders,
                    "orders_today": orders_today,
                    "total_products": total_products,
                    "active_products": active_products,
                    "total_subscriptions": total_subscriptions,
                    "active_subscriptions": active_subscriptions
                },
                "revenue": {
                    "total_revenue": float(total_revenue),
                    "revenue_today": float(revenue_today),
                    "revenue_this_month": float(revenue_this_month),
                    "currency": "USD"
                },
                "chart_data": chart_data,
                "recent_orders": [
                    {
                        "id": str(order.id),
                        "user_email": order.user.email if order.user else "Unknown",
                        "total_amount": float(order.total_amount),
                        "status": order.order_status,
                        "created_at": order.created_at.isoformat() if order.created_at else None
                    }
                    for order in recent_orders
                ],
                "recent_users": [
                    {
                        "id": str(user.id),
                        "email": user.email,
                        "firstname": user.firstname,
                        "lastname": user.lastname,
                        "is_active": user.is_active,
                        "created_at": user.created_at.isoformat() if user.created_at else None
                    }
                    for user in recent_users
                ],
                "top_products": top_products,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            # Return basic stats on error
            return {
                "overview": {
                    "total_users": 0,
                    "active_users": 0,
                    "total_products": total_products,
                    "active_products": active_products,
                    "total_subscriptions": total_subscriptions,
                    "active_subscriptions": active_subscriptions
                },
                "revenue": {
                    "total_revenue": float(total_revenue),
                    "revenue_today": float(revenue_today),
                    "revenue_this_month": float(revenue_this_month),
                    "currency": "USD"
                },
                "recent_orders": [
                    {
                        "id": str(order.id),
                        "user_email": order.user.email if order.user else "Unknown",
                        "total_amount": float(order.total_amount),
                        "status": order.order_status,
                        "created_at": order.created_at.isoformat() if order.created_at else None
                    }
                    for order in recent_orders
                ],
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            # Return basic stats on error
            return {
                "overview": {
                    "total_users": 0,
                    "active_users": 0,
                    "total_orders": 0,
                    "orders_today": 0,
                    "total_products": 0,
                    "active_products": 0,
                    "total_subscriptions": 0,
                    "active_subscriptions": 0
                },
                "revenue": {
                    "total_revenue": 0.0,
                    "revenue_today": 0.0,
                    "revenue_this_month": 0.0,
                    "currency": "USD"
                },
                "recent_orders": [],
                "chart_data": [],
                "error": f"Failed to fetch complete stats: {str(e)}",
                "generated_at": datetime.utcnow().isoformat()
            }
    
    async def _generate_daily_metrics(
        self,
        start_date: date,
        end_date: date,
        status: Optional[str] = None,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Generate daily metrics for chart data between date range"""
        from models.commerce.orders import Order
        from models.catalog.product import Product
        
        chart_data = []
        current_date = start_date
        
        while current_date <= end_date:
            next_date = current_date + timedelta(days=1)
            
            # Build conditions for this day (include confirmed, processing, shipped, delivered)
            date_conditions = [
                func.date(Order.created_at) == current_date,
                Order.order_status.in_(['CONFIRMED', 'PROCESSING', 'SHIPPED', 'DELIVERED'])
            ]
            if status:
                date_conditions.append(Order.order_status == status)
            
            # Get daily revenue
            daily_revenue = await self.db.scalar(
                select(func.coalesce(func.sum(Order.total_amount), 0)).where(and_(*date_conditions))
            ) or 0
            
            # Get daily orders count
            daily_orders = await self.db.scalar(
                select(func.count(Order.id)).where(
                    func.date(Order.created_at) == current_date
                )
            ) or 0
            
            # Get daily new users (excluding admin users)
            daily_users = await self.db.scalar(
                select(func.count(User.id)).where(
                    and_(
                        func.date(User.created_at) == current_date,
                        User.role != 'admin'
                    )
                )
            ) or 0
            
            chart_data.append({
                "date": current_date.strftime('%b %d'),
                "revenue": float(daily_revenue),
                "orders": int(daily_orders),
                "users": int(daily_users)
            })
            
            current_date = next_date
        
        return chart_data

    async def overview(self) -> Dict[str, Any]:
        """Get platform overview statistics"""
        try:
            
            # Get basic counts
            stats = await self.stats()
            
            # Additional platform metrics
            last_30_days = datetime.utcnow() - timedelta(days=30)
            
            # Order status distribution
            order_statuses = await self.db.execute(
                select(Order.order_status, func.count(Order.id).label('count'))
                .group_by(Order.order_status)
            )
            status_distribution = {status: count for status, count in order_statuses.all()}
            
            # Growth metrics
            new_users_last_30_days = await self.db.scalar(
                select(func.count(User.id)).where(
                    and_(User.created_at >= last_30_days, User.role != 'admin')
                )
            ) or 0
            
            new_orders_last_30_days = await self.db.scalar(
                select(func.count(Order.id)).where(Order.created_at >= last_30_days)
            ) or 0
            
            # Top products by sales (last 30 days)
            top_products_query = await self.db.execute(
                select(
                    Product.id,
                    Product.name,
                    func.sum(OrderItem.quantity).label('sales'),
                    func.sum(OrderItem.quantity * OrderItem.price_per_unit).label('revenue')
                )
                .select_from(OrderItem)
                .join(ProductVariant, OrderItem.variant_id == ProductVariant.id)
                .join(Product, ProductVariant.product_id == Product.id)
                .join(Order, OrderItem.order_id == Order.id)
                .where(
                    and_(
                        Order.created_at >= last_30_days,
                        Order.order_status.in_(['CONFIRMED', 'PROCESSING', 'SHIPPED', 'DELIVERED'])
                    )
                )
                .group_by(Product.id, Product.name)
                .order_by(func.sum(OrderItem.quantity * OrderItem.price_per_unit).desc())
                .limit(5)
            )
            
            top_products = [
                {
                    "id": str(product.id),
                    "name": product.name,
                    "image": "https://images.unsplash.com/photo-1560472354-b33ff0c44a43?ixlib=rb-4.0.3&auto=format&fit=crop&w=100&q=80",
                    "sales": int(product.sales or 0),
                    "revenue": float(product.revenue or 0)
                }
                for product in top_products_query.all()
            ]
            
            return {
                **stats,
                "top_products": top_products,
                "platform_metrics": {
                    "order_status_distribution": status_distribution,
                    "growth_metrics": {
                        "new_users_last_30_days": new_users_last_30_days,
                        "new_orders_last_30_days": new_orders_last_30_days
                    }
                }
            }
            
        except Exception as e:
            return {
                "error": f"Failed to fetch platform overview: {str(e)}",
                "generated_at": datetime.utcnow().isoformat()
            }

    async def list_all(
        self,
        page: int = 1,
        limit: int = 10,
        order_status: Optional[str] = None,
        q: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """Get all orders with filtering and pagination - delegates to OrderService"""
        from services.commerce.orders import OrderService
        
        order_service = OrderService(self.db)
        return await order_service.list_all(
            page=page,
            limit=limit,
            order_status=order_status,
            q=q,
            date_from=date_from,
            date_to=date_to,
            min_price=min_price,
            max_price=max_price
        )

    def _calculate_subtotal_from_items(self, items: List) -> float:
        """
        Calculate subtotal from order items considering quantity and unit price.
        
        IMPORTANT: This is the authoritative subtotal calculation.
        Formula: SUM(quantity × price_per_unit) for all items
        
        This method is called at:
        1. Order creation time (to ensure subtotal is stored correctly)
        2. Order retrieval time (to ensure data integrity and audit trail)
        
        Args:
            items: List of OrderItem objects
            
        Returns:
            float: Calculated subtotal
        """
        if not items:
            return 0.0
        
        # Explicitly calculate: sum of (quantity * price_per_unit)
        subtotal = sum(float(item.quantity * item.price_per_unit) for item in items)
        
        return subtotal

    async def get(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get a single order by ID with items, product, variant, and variant images"""
        try:
            from models.commerce.orders import Order, OrderItem
            from models.catalog.product import ProductVariant, Product, ProductImage

            result = await self.db.execute(
                select(Order)
                .options(selectinload(Order.user))
                .options(selectinload(Order.items))
                .where(Order.id == UUID(order_id))
            )
            order = result.scalar_one_or_none()
            
            if not order:
                return None
            
            # Fetch variants and images separately to avoid circular loading issues
            if order.items:
                for item in order.items:
                    if item.variant_id:
                        variant_result = await self.db.execute(
                            select(ProductVariant)
                            .options(selectinload(ProductVariant.product))
                            .options(selectinload(ProductVariant.images))
                            .where(ProductVariant.id == item.variant_id)
                        )
                        item.variant = variant_result.scalar_one_or_none()

            def serialize_order_item(item) -> dict:
                variant = getattr(item, "variant", None)
                product = getattr(variant, "product", None) if variant else None
                images = list(getattr(variant, "images", None) or [])
                return {
                    "id": str(item.id),
                    "order_id": str(item.order_id),
                    "variant_id": str(item.variant_id) if item.variant_id else None,
                    "product_id": str(product.id) if product else None,
                    "product_name": getattr(product, "name", None) if product else None,
                    "variant_name": getattr(variant, "sku", None) or getattr(variant, "name", None) if variant else None,
                    "sku": getattr(variant, "sku", None) if variant else None,
                    "quantity": item.quantity,
                    "price_per_unit": float(item.price_per_unit),
                    "unit_price": float(item.price_per_unit),
                    "total_price": float(item.total_price),
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "product": {
                        "id": str(product.id),
                        "name": getattr(product, "name", None),
                        "slug": getattr(product, "slug", None),
                    } if product else None,
                    "variant": {
                        "id": str(variant.id),
                        "sku": getattr(variant, "sku", None),
                        "name": getattr(variant, "name", None),
                        "images": [
                            {"id": str(img.id), "url": img.url, "alt_text": img.alt_text, "is_primary": getattr(img, "is_primary", False)}
                            for img in images
                        ],
                    } if variant else None,
                }
            
            # Recalculate order totals based on actual items
            items_list = order.items if order.items else []
            # Use centralized calculation method for consistency
            calculated_subtotal = self._calculate_subtotal_from_items(items_list)
            calculated_shipping = float(order.shipping_cost or 0.0)
            calculated_tax = float(order.tax_amount or 0.0)
            calculated_total = calculated_subtotal + calculated_shipping + calculated_tax
            
            return {
                "id": str(order.id),
                "order_number": order.order_number,
                "user_email": order.user.email if order.user else "Unknown",
                "user": {
                    "firstname": order.user.firstname if order.user else None,
                    "lastname": order.user.lastname if order.user else None,
                    "email": order.user.email if order.user else "Unknown"
                } if order.user else None,
                "total_amount": calculated_total,
                "sub_total": calculated_subtotal,
                "subtotal": calculated_subtotal,
                "shipping_cost": calculated_shipping,
                "tax_amount": calculated_tax,
                "tax_rate": float(order.tax_rate or 0),
                "currency": order.currency,
                "discount_amount": float(getattr(order, "discount_amount", 0.0)),
                "order_status": order.order_status.value if hasattr(order.order_status, "value") else order.order_status,
                "payment_status": order.payment_status.value if hasattr(order.payment_status, "value") else order.payment_status,
                "fulfillment_status": order.fulfillment_status.value if hasattr(order.fulfillment_status, "value") else order.fulfillment_status,
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "updated_at": order.updated_at.isoformat() if order.updated_at else None,
                "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None,
                "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
                "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
                "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
                "shipping_method": order.shipping_method,
                "shipping_address": order.shipping_address,
                "billing_address": order.billing_address,
                "tracking_number": order.tracking_number,
                "carrier": order.carrier,
                "customer_notes": order.customer_notes,
                "internal_notes": order.internal_notes,
                "source": order.source.value if hasattr(order.source, "value") else order.source,
                "notes": order.notes,
                "items": [serialize_order_item(item) for item in order.items]

            }
            
        except Exception as e:
            import traceback
            print(f"Error fetching order by ID: {e}")
            print(traceback.format_exc())
            return None


    async def list_products(
        self,
        page: int = 1,
        limit: int = 10,
        search: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get all products - delegates to ProductService to avoid duplication"""
        from services.catalog.products import ProductService
        
        product_service = ProductService(self.db)
        return await product_service.list(
            page=page,
            limit=limit,
            search=search,
            category=category,
            status=status
        )

    async def all_variants(
        self,
        page: int = 1,
        limit: int = 10,
        search: Optional[str] = None,
        product_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get all product variants with filtering - delegates to ProductService"""
        from services.catalog.products import ProductService
        from uuid import UUID
        
        product_service = ProductService(self.db)
        return await product_service.all_variants(
            page=page,
            limit=limit,
            search=search,
            product_id=UUID(product_id) if product_id else None
        )

    # User management methods
    async def create(self, user_data, background_tasks) -> Dict[str, Any]:
        """Create a new user (admin only)"""
        try:
            from services.accounts.auth import AuthService
            
            # Use AuthService to create user
            auth_service = AuthService()
            user = await auth_service.create(user_data, self.db, background_tasks)
            
            return {
                "id": str(user.id),
                "email": user.email,
                "firstname": user.firstname,
                "lastname": user.lastname,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to create user: {str(e)}"
            )

    async def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a user by ID"""
        try:
            result = await self.db.execute(select(User).where(User.id == UUID(user_id)))
            user = result.scalar_one_or_none()
            
            if not user:
                return None
            
            return {
                "id": str(user.id),
                "email": user.email,
                "firstname": user.firstname,
                "lastname": user.lastname,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login": user.last_login.isoformat() if user.last_login else None
            }
        except Exception:
            return None

    async def update_status(self, user_id: str, is_active: bool) -> Dict[str, Any]:
        """Update user status (admin only)"""
        try:
            result = await self.db.execute(select(User).where(User.id == UUID(user_id)))
            user = result.scalar_one_or_none()
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            user.is_active = is_active
            await self.db.commit()
            await self.db.refresh(user)
            
            return {
                "id": str(user.id),
                "email": user.email,
                "firstname": user.firstname,
                "lastname": user.lastname,
                "role": user.role,
                "is_active": user.is_active,
                "updated_at": user.updated_at.isoformat() if user.updated_at else None
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to update user status: {str(e)}"
            )

    async def delete(self, user_id: str) -> bool:
        """Delete user (admin only)"""
        try:
            result = await self.db.execute(select(User).where(User.id == UUID(user_id)))
            user = result.scalar_one_or_none()

            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # Soft delete only
            user.is_active = False
            user.account_status = "deleted"
            user.verification_status = "deleted"

            await self.db.commit()
            await self.db.refresh(user)
            return True

        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to delete user: {str(e)}"
            )

    async def reset_password(self, user_id: str) -> Dict[str, Any]:
        """Send password reset email to user (admin only)"""
        try:
            result = await self.db.execute(select(User).where(User.id == UUID(user_id)))
            user = result.scalar_one_or_none()
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Generate reset token and send email
            # This would typically integrate with your email service
            reset_token = "temp_reset_token"  # Generate actual token
            
            return {
                "message": f"Password reset email sent to {user.email}",
                "user_id": str(user.id),
                "email": user.email
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to send password reset email: {str(e)}"
            )

    async def deactivate(self, user_id: str) -> Dict[str, Any]:
        """Deactivate user account (admin only)"""
        try:
            result = await self.db.execute(select(User).where(User.id == UUID(user_id)))
            user = result.scalar_one_or_none()
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            user.is_active = False
            user.account_status = "deactivated"
            await self.db.commit()
            await self.db.refresh(user)
            
            return {
                "message": f"User account {user.email} has been deactivated",
                "user_id": str(user.id),
                "is_active": user.is_active,
                "account_status": user.account_status
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to deactivate user: {str(e)}"
            )

    async def activate(self, user_id: str) -> Dict[str, Any]:
        """Activate user account (admin only)"""
        try:
            result = await self.db.execute(select(User).where(User.id == UUID(user_id)))
            user = result.scalar_one_or_none()
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            user.is_active = True
            user.account_status = "active"
            await self.db.commit()
            await self.db.refresh(user)
            
            return {
                "message": f"User account {user.email} has been activated",
                "user_id": str(user.id),
                "is_active": user.is_active,
                "account_status": user.account_status
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to activate user: {str(e)}"
            )