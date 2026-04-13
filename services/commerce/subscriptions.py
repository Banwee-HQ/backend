"""
Simplified Subscription Service
Handles subscription creation, updates, and pricing calculations
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
from models.commerce.subscriptions import Subscription
from models.catalog.product import ProductVariant
from models.accounts.user import Address
from models.commerce.promocode import Promocode
from uuid import UUID
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from decimal import Decimal
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)


class SubscriptionService:
    """Simplified subscription service with dynamic pricing"""
    
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        user_id: UUID,
        name: str,
        variant_ids: List[str],
        variant_quantities: Optional[Dict[str, int]] = None,
        delivery_type: str = "standard",
        delivery_address_id: Optional[UUID] = None,
        billing_cycle: str = "monthly",
        currency: str = "USD",
        discount_code: Optional[str] = None
    ) -> Subscription:
        """Create a new subscription"""
        
        # Validate variants
        variant_uuids = [UUID(vid) for vid in variant_ids]
        variant_result = await self.db.execute(
            select(ProductVariant)
            .where(ProductVariant.id.in_(variant_uuids))
            .options(selectinload(ProductVariant.product))
        )
        variants = variant_result.scalars().all()
        
        if len(variants) != len(variant_uuids):
            raise HTTPException(status_code=400, detail="Some variants not found")
        
        # Get customer address for tax calculation
        customer_address = None
        if delivery_address_id:
            address_result = await self.db.execute(
                select(Address).where(
                    and_(Address.id == delivery_address_id, Address.user_id == user_id)
                )
            )
            address = address_result.scalar_one_or_none()
            if address:
                customer_address = {
                    "street": address.street,
                    "city": address.city,
                    "state": address.state,
                    "country": address.country,
                    "post_code": address.post_code
                }
        
        # Calculate pricing at creation
        pricing = await self._calculate_pricing(
            variants,
            variant_quantities or {},
            delivery_type,
            customer_address,
            currency,
            user_id,
            discount_code
        )
        
        # Set billing dates
        now = datetime.now(timezone.utc)
        if billing_cycle == "weekly":
            period_end = now + timedelta(weeks=1)
        elif billing_cycle == "yearly":
            from dateutil.relativedelta import relativedelta
            period_end = now + relativedelta(years=1)
        else:  # monthly
            from dateutil.relativedelta import relativedelta
            period_end = now + relativedelta(months=1)
        
        # Create subscription
        subscription = Subscription(
            user_id=user_id,
            name=name,
            status="active",
            currency=currency,
            billing_cycle=billing_cycle,
            auto_renew=True,
            current_period_start=now,
            current_period_end=period_end,
            next_billing_date=period_end,
            delivery_type=delivery_type,
            delivery_address_id=delivery_address_id,
            variant_ids=variant_ids,
            subscription_metadata={"variant_quantities": variant_quantities or {vid: 1 for vid in variant_ids}},
            # Historical prices at creation
            price_at_creation=pricing["total"],
            variant_prices_at_creation=pricing["variant_prices"],
            shipping_amount_at_creation=pricing["shipping"],
            tax_amount_at_creation=pricing["tax"],
            tax_rate_at_creation=pricing["tax_rate"],
            # Current prices (same as creation initially)
            current_variant_prices=pricing["variant_prices"],
            current_shipping_amount=pricing["shipping"],
            current_tax_amount=pricing["tax"],
            current_tax_rate=pricing["tax_rate"],
            # Discount
            discount_id=pricing.get("discount_id"),
            discount_type=pricing.get("discount_type"),
            discount_value=pricing.get("discount_value"),
            discount_code=pricing.get("discount_code")
        )

        self.db.add(subscription)
        await self.db.flush()

        # Add products to association table
        from models.commerce.subscriptions import SubscriptionProductAssociation
        for variant in variants:
            association = SubscriptionProductAssociation(
                subscription_id=subscription.id,
                product_variant_id=variant.id
            )
            self.db.add(association)
        
        await self.db.commit()
        await self.db.refresh(subscription)
        
        return subscription

    async def _calculate_pricing(
        self,
        variants: List[ProductVariant],
        variant_quantities: Dict[str, int],
        delivery_type: str,
        customer_address: Optional[Dict],
        currency: str,
        user_id: UUID,
        discount_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """Calculate subscription pricing"""
        
        # Calculate variant prices
        variant_prices = []
        subtotal = Decimal('0.00')
        
        for variant in variants:
            qty = variant_quantities.get(str(variant.id), 1)
            price = Decimal(str(variant.current_price or 0))
            
            if price <= 0:
                logger.warning(f"Variant {variant.id} has zero price, using minimum")
                price = Decimal('9.99')
            
            line_total = price * qty
            subtotal += line_total
            
            variant_prices.append({
                "id": str(variant.id),
                "price": float(price),
                "qty": qty
            })
        
        # Get shipping cost from database
        shipping_cost = await self._get_shipping_cost(delivery_type)
        
        # Calculate tax
        tax_amount = Decimal('0.00')
        tax_rate = Decimal('0.00')
        
        if customer_address:
            try:
                from services.commerce.tax import TaxService
                tax_service = TaxService(self.db)
                
                country = customer_address.get('country', '')
                state = customer_address.get('state', '')
                
                tax_rate_value = await tax_service.rate(country, state)
                tax_amount = float(subtotal + shipping_cost) * tax_rate_value
                tax_rate = Decimal(str(tax_rate_value))
                
            except Exception as e:
                logger.warning(f"Tax calculation failed: {e}")
        
        # Apply discount
        discount_amount = Decimal('0.00')
        discount_id = None
        discount_type = None
        discount_value = None
        discount_code_used = None
        
        if discount_code:
            try:
                promo_result = await self.db.execute(
                    select(Promocode).where(
                        and_(
                            Promocode.code == discount_code,
                            Promocode.is_active == True
                        )
                    )
                )
                promo = promo_result.scalar_one_or_none()
                
                if promo:
                    discount_id = promo.id
                    discount_type = promo.discount_type
                    discount_value = promo.value
                    discount_code_used = promo.code
                    
                    if promo.discount_type == "percentage":
                        discount_amount = subtotal * (Decimal(str(promo.value)) / 100)
                    else:  # fixed
                        discount_amount = Decimal(str(promo.value))
                        
            except Exception as e:
                logger.warning(f"Discount application failed: {e}")
        
        # Calculate total
        total = subtotal + shipping_cost + tax_amount - discount_amount
        
        return {
            "variant_prices": variant_prices,
            "subtotal": float(subtotal),
            "shipping": float(shipping_cost),
            "tax": float(tax_amount),
            "tax_rate": float(tax_rate),
            "discount": float(discount_amount),
            "total": float(total),
            "discount_id": discount_id,
            "discount_type": discount_type,
            "discount_value": discount_value,
            "discount_code": discount_code_used
        }

    async def _get_shipping_cost(self, delivery_type: str) -> Decimal:
        """Get shipping cost from database"""
        from models.commerce.shipping import ShippingMethod
        
        result = await self.db.execute(
            select(ShippingMethod).where(ShippingMethod.is_active == True)
        )
        methods = result.scalars().all()
        
        # Find matching method
        delivery_type_lower = delivery_type.lower()
        for method in methods:
            if delivery_type_lower in method.name.lower():
                return Decimal(str(method.price))
        
        # Fallback to cheapest
        if methods:
            cheapest = min(methods, key=lambda m: m.price)
            return Decimal(str(cheapest.price))
        
        # Final fallback
        return Decimal('8.99')

    async def get(self, subscription_id: UUID, user_id: Optional[UUID] = None) -> Optional[Subscription]:
        """Get subscription by ID"""
        query = select(Subscription).where(Subscription.id == subscription_id).options(
            selectinload(Subscription.products).selectinload(ProductVariant.product),
            selectinload(Subscription.products).selectinload(ProductVariant.images)
        )
        
        if user_id:
            query = query.where(Subscription.user_id == user_id)
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self, 
        user_id: Optional[UUID] = None, 
        status: Optional[str] = None,
        search: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1, 
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get paginated subscriptions. If user_id is None, returns all subscriptions (admin)."""
        from sqlalchemy import func as sqlfunc
        from models.accounts.user import User

        offset = (page - 1) * limit

        # Build base query
        if user_id:
            # User-specific query
            base_query = select(Subscription).where(Subscription.user_id == user_id).options(
                selectinload(Subscription.products).selectinload(ProductVariant.product),
                selectinload(Subscription.products).selectinload(ProductVariant.images)
            )
            count_query = select(sqlfunc.count()).select_from(Subscription).where(Subscription.user_id == user_id)
        else:
            # Admin query - includes user info
            base_query = (
                select(Subscription, User)
                .join(User, Subscription.user_id == User.id)
                .options(selectinload(Subscription.products))
            )
            count_query = select(sqlfunc.count()).select_from(Subscription)

        # Apply filters
        if status:
            base_query = base_query.where(Subscription.status == status)
            count_query = count_query.where(Subscription.status == status)

        # Apply search filter (admin only with user join)
        if search and not user_id:
            search_term = f"%{search}%"
            from sqlalchemy import or_
            base_query = base_query.where(
                or_(
                    User.email.ilike(search_term),
                    User.firstname.ilike(search_term),
                    User.lastname.ilike(search_term),
                )
            )

        # Apply date filters
        if date_from:
            try:
                from_date = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                base_query = base_query.where(Subscription.created_at >= from_date)
            except ValueError:
                pass

        if date_to:
            try:
                to_date = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                base_query = base_query.where(Subscription.created_at <= to_date)
            except ValueError:
                pass

        # Apply sorting
        sort_column = Subscription.created_at
        if sort_by == "next_billing_date":
            sort_column = Subscription.next_billing_date
        elif sort_by == "status":
            sort_column = Subscription.status

        if sort_order == "asc":
            base_query = base_query.order_by(sort_column.asc())
        else:
            base_query = base_query.order_by(sort_column.desc())

        # Get total count
        total = await self.db.scalar(count_query) or 0

        # Execute query with pagination
        result = await self.db.execute(base_query.offset(offset).limit(limit))

        # Format results
        if user_id:
            subscriptions = result.scalars().all()
            subscriptions_data = [sub.to_dict(include_products=True) for sub in subscriptions]
        else:
            rows = result.all()
            subscriptions_data = []
            for subscription, user in rows:
                sub_dict = subscription.to_dict(include_products=True)
                sub_dict["user"] = {
                    "id": str(user.id),
                    "name": f"{user.firstname} {user.lastname}",
                    "email": user.email
                }
                subscriptions_data.append(sub_dict)

        return {
            "data": subscriptions_data,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": max(1, (total + limit - 1) // limit) if limit else 1
            }
        }

    async def update(
        self,
        subscription_id: UUID,
        user_id: UUID,
        name: Optional[str] = None,
        delivery_type: Optional[str] = None,
        delivery_address_id: Optional[UUID] = None,
        auto_renew: Optional[bool] = None,
        variant_ids: Optional[List[str]] = None,
        variant_quantities: Optional[Dict[str, int]] = None
    ) -> Subscription:
        """Update subscription"""
        subscription = await self.get(subscription_id, user_id)
        
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        
        if subscription.status not in ["active", "paused"]:
            raise HTTPException(status_code=400, detail="Cannot update inactive subscription")
        
        if name:
            subscription.name = name
        
        if delivery_type:
            subscription.delivery_type = delivery_type
        
        if delivery_address_id:
            subscription.delivery_address_id = delivery_address_id
        
        if auto_renew is not None:
            subscription.auto_renew = auto_renew

        if variant_ids:
            subscription.variant_ids = variant_ids

            # Update association table
            from models.commerce.subscriptions import SubscriptionProductAssociation
            await self.db.execute(
                delete(SubscriptionProductAssociation).where(
                    SubscriptionProductAssociation.subscription_id == subscription.id
                )
            )

            variant_uuids = [UUID(vid) for vid in variant_ids]
            variant_result = await self.db.execute(
                select(ProductVariant).where(ProductVariant.id.in_(variant_uuids))
            )
            variants = variant_result.scalars().all()

            for variant in variants:
                association = SubscriptionProductAssociation(
                    subscription_id=subscription.id,
                    product_variant_id=variant.id
                )
                self.db.add(association)
        
        if variant_quantities:
            if not subscription.subscription_metadata:
                subscription.subscription_metadata = {}
            subscription.subscription_metadata["variant_quantities"] = variant_quantities
        
        await self.db.commit()
        await self.db.refresh(subscription)
        
        return subscription

    async def cancel(self, subscription_id: UUID, user_id: UUID, reason: Optional[str] = None) -> Subscription:
        """Cancel subscription"""
        subscription = await self.get(subscription_id, user_id)
        
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        
        subscription.status = "cancelled"
        subscription.cancelled_at = datetime.now(timezone.utc)
        subscription.auto_renew = False
        
        if reason:
            subscription.pause_reason = f"Cancelled: {reason}"
        
        await self.db.commit()
        await self.db.refresh(subscription)
        
        return subscription

    async def pause(self, subscription_id: UUID, user_id: UUID, reason: Optional[str] = None) -> Subscription:
        """Pause subscription"""
        subscription = await self.get(subscription_id, user_id)
        
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        
        if subscription.status != "active":
            raise HTTPException(status_code=400, detail="Can only pause active subscriptions")
        
        subscription.status = "paused"
        subscription.paused_at = datetime.now(timezone.utc)
        subscription.pause_reason = reason
        
        await self.db.commit()
        await self.db.refresh(subscription)
        
        return subscription

    async def resume(self, subscription_id: UUID, user_id: UUID) -> Subscription:
        """Resume subscription"""
        subscription = await self.get(subscription_id, user_id)
        
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        
        if subscription.status not in ["paused", "cancelled"]:
            raise HTTPException(status_code=400, detail="Can only resume paused or cancelled subscriptions")
        
        subscription.status = "active"
        subscription.paused_at = None
        subscription.pause_reason = None
        subscription.cancelled_at = None
        subscription.next_billing_date = datetime.now(timezone.utc) + timedelta(days=30)
        
        await self.db.commit()
        await self.db.refresh(subscription)
        
        return subscription

    async def recalc_pricing(self, subscription: Subscription) -> Dict[str, Any]:
        """Recalculate current pricing for a subscription"""
        
        # Get current variants
        variant_uuids = [UUID(vid) for vid in subscription.variant_ids]
        variant_result = await self.db.execute(
            select(ProductVariant).where(ProductVariant.id.in_(variant_uuids))
        )
        variants = variant_result.scalars().all()
        
        # Get quantities
        variant_quantities = subscription.subscription_metadata.get("variant_quantities", {}) if subscription.subscription_metadata else {}
        
        # Get customer address
        customer_address = None
        if subscription.delivery_address_id:
            address_result = await self.db.execute(
                select(Address).where(Address.id == subscription.delivery_address_id)
            )
            address = address_result.scalar_one_or_none()
            if address:
                customer_address = {
                    "street": address.street,
                    "city": address.city,
                    "state": address.state,
                    "country": address.country,
                    "post_code": address.post_code
                }
        
        # Calculate current pricing
        pricing = await self._calculate_pricing(
            variants,
            variant_quantities,
            subscription.delivery_type or "standard",
            customer_address,
            subscription.currency or "USD",
            subscription.user_id,
            subscription.discount_code
        )
        
        # Update current pricing fields
        subscription.current_variant_prices = pricing["variant_prices"]
        subscription.current_shipping_amount = pricing["shipping"]
        subscription.current_tax_amount = pricing["tax"]
        subscription.current_tax_rate = pricing["tax_rate"]
        
        await self.db.commit()
        
        return pricing

    # -------------------------------------------------------------------------

    async def delete(self, subscription_id: UUID, user_id: UUID) -> bool:
        subscription = await self.get(subscription_id, user_id)
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        await self.db.delete(subscription)
        await self.db.commit()
        return True

    async def add_products(self, subscription_id: UUID, variant_ids: List[UUID], user_id: UUID) -> Subscription:
        """Add products to a subscription"""
        subscription = await self.get(subscription_id, user_id)
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")

        from models.commerce.subscriptions import SubscriptionProductAssociation

        existing_ids = {str(v.id) for v in subscription.products}
        for vid in variant_ids:
            if str(vid) not in existing_ids:
                association = SubscriptionProductAssociation(
                    subscription_id=subscription.id,
                    product_variant_id=vid
                )
                self.db.add(association)
                if subscription.variant_ids is None:
                    subscription.variant_ids = []
                if str(vid) not in subscription.variant_ids:
                    subscription.variant_ids = subscription.variant_ids + [str(vid)]
        
        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription

    async def remove_products(self, subscription_id: UUID, variant_ids: List[UUID], user_id: UUID) -> Subscription:
        """Remove products from a subscription"""
        subscription = await self.get(subscription_id, user_id)
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")

        from models.commerce.subscriptions import SubscriptionProductAssociation

        for vid in variant_ids:
            await self.db.execute(
                delete(SubscriptionProductAssociation).where(
                    and_(
                        SubscriptionProductAssociation.subscription_id == subscription.id,
                        SubscriptionProductAssociation.product_variant_id == vid
                    )
                )
            )
        if subscription.variant_ids:
            subscription.variant_ids = [v for v in subscription.variant_ids if v not in [str(vid) for vid in variant_ids]]
        
        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription

    async def set_quantity(self, subscription_id: UUID, variant_id: UUID, quantity: int, user_id: UUID) -> Subscription:
        subscription = await self.get(subscription_id, user_id)
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        meta = dict(subscription.subscription_metadata or {})
        quantities = dict(meta.get("variant_quantities", {}))
        quantities[str(variant_id)] = quantity
        subscription.subscription_metadata = {**meta, "variant_quantities": quantities}
        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription

    async def adjust_quantity(self, subscription_id: UUID, variant_id: UUID, change: int, user_id: UUID) -> Subscription:
        subscription = await self.get(subscription_id, user_id)
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        meta = dict(subscription.subscription_metadata or {})
        quantities = dict(meta.get("variant_quantities", {}))
        quantities[str(variant_id)] = max(1, quantities.get(str(variant_id), 1) + change)
        subscription.subscription_metadata = {**meta, "variant_quantities": quantities}
        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription

    async def get_quantities(self, subscription_id: UUID, user_id: UUID) -> Dict[str, int]:
        subscription = await self.get(subscription_id, user_id)
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        if subscription.subscription_metadata:
            return subscription.subscription_metadata.get("variant_quantities", {})
        return {}

    async def get_orders(self, subscription_id: UUID, user_id: UUID, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        from models.commerce.orders import Order
        from sqlalchemy import func as sqlfunc
        subscription = await self.get(subscription_id, user_id)
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        total = await self.db.scalar(
            select(sqlfunc.count()).select_from(Order).where(Order.subscription_id == subscription_id)
        ) or 0
        result = await self.db.execute(
            select(Order).where(Order.subscription_id == subscription_id)
            .order_by(Order.created_at.desc())
            .offset((page - 1) * limit).limit(limit)
        )
        orders = result.scalars().all()
        return {
            "orders": [o.to_dict() for o in orders],
            "total": total,
            "page": page,
            "limit": limit,
            "pages": max(1, (total + limit - 1) // limit)
        }

    async def _calc_cost(
        self,
        variants: List[ProductVariant],
        delivery_type: str,
        customer_address: Optional[Dict],
        currency: str,
        user_id: UUID,
        variant_quantities: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        return await self._calculate_pricing(
            variants=variants,
            variant_quantities=variant_quantities or {},
            delivery_type=delivery_type,
            customer_address=customer_address,
            currency=currency,
            user_id=user_id,
        )
