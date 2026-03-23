from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc
from sqlalchemy.orm import selectinload, joinedload
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta
from decimal import Decimal

from models.variant_tracking import (
    VariantTrackingEntry, VariantPriceHistory, 
    VariantAnalytics, VariantSubstitution
)
from models.product import ProductVariant, Product
from models.subscriptions import Subscription
from models.inventories import Inventory
from core.errors import APIException


class VariantTrackingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def track_variant_subscription_addition(
        self,
        variant_id: UUID,
        subscription_id: UUID,
        price_at_time: float,
        currency: str = "USD",
        metadata: Optional[Dict[str, Any]] = None
    ) -> VariantTrackingEntry:
        """
        Track when a variant is added to a subscription with ID, price, and timestamp recording.
        Requirements: 3.1
        """
        # Verify variant and subscription exist
        variant_query = select(ProductVariant).where(ProductVariant.id == variant_id)
        variant_result = await self.db.execute(variant_query)
        variant = variant_result.scalar_one_or_none()
        
        if not variant:
            raise APIException(status_code=404, message="Product variant not found")
        
        subscription_query = select(Subscription).where(Subscription.id == subscription_id)
        subscription_result = await self.db.execute(subscription_query)
        subscription = subscription_result.scalar_one_or_none()
        
        if not subscription:
            raise APIException(status_code=404, message="Subscription not found")
        
        # Create tracking entry
        tracking_entry = VariantTrackingEntry(
            variant_id=variant_id,
            subscription_id=subscription_id,
            price_at_time=price_at_time,
            currency=currency,
            action_type="added",
            tracking_timestamp=datetime.utcnow(),
            entry_metadata=metadata or {}
        )
        
        self.db.add(tracking_entry)
        await self.db.commit()
        await self.db.refresh(tracking_entry)
        
        return tracking_entry

    async def get_variant_analytics(
        self,
        variant_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period_type: str = "daily"
    ) -> Dict[str, Any]:
        """
        Get variant analytics for popularity, revenue, and churn analysis.
        Requirements: 3.3
        """
        # Set default date range if not provided
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)  # Default to last 30 days
        
        # Get basic variant info
        variant_query = select(ProductVariant).options(
            joinedload(ProductVariant.product)
        ).where(ProductVariant.id == variant_id)
        variant_result = await self.db.execute(variant_query)
        variant = variant_result.scalar_one_or_none()
        
        if not variant:
            raise APIException(status_code=404, message="Product variant not found")
        
        # Get tracking entries for the period
        tracking_query = select(VariantTrackingEntry).where(
            and_(
                VariantTrackingEntry.variant_id == variant_id,
                VariantTrackingEntry.tracking_timestamp >= start_date,
                VariantTrackingEntry.tracking_timestamp <= end_date
            )
        ).order_by(VariantTrackingEntry.tracking_timestamp.desc())
        
        tracking_result = await self.db.execute(tracking_query)
        tracking_entries = tracking_result.scalars().all()
        
        # Calculate metrics
        total_subscriptions = len([e for e in tracking_entries if e.action_type == "added"])
        canceled_subscriptions = len([e for e in tracking_entries if e.action_type == "removed"])
        
        # Calculate revenue
        total_revenue = sum(e.price_at_time for e in tracking_entries if e.action_type == "added")
        
        # Calculate average subscription duration (simplified)
        active_subscriptions_query = select(func.count(Subscription.id)).where(
            and_(
                Subscription.variant_ids.contains([str(variant_id)]),
                Subscription.status == "active"
            )
        )
        active_subscriptions_result = await self.db.execute(active_subscriptions_query)
        active_subscriptions = active_subscriptions_result.scalar() or 0
        
        # Calculate churn rate
        churn_rate = (canceled_subscriptions / total_subscriptions * 100) if total_subscriptions > 0 else 0.0
        
        # Get popularity rank (simplified - based on total subscriptions)
        popularity_rank_query = select(
            func.count().label("subscription_count"),
            VariantTrackingEntry.variant_id
        ).where(
            and_(
                VariantTrackingEntry.action_type == "added",
                VariantTrackingEntry.tracking_timestamp >= start_date,
                VariantTrackingEntry.tracking_timestamp <= end_date
            )
        ).group_by(VariantTrackingEntry.variant_id).order_by(desc("subscription_count"))
        
        popularity_result = await self.db.execute(popularity_rank_query)
        popularity_data = popularity_result.all()
        
        popularity_rank = None
        for idx, (count, v_id) in enumerate(popularity_data, 1):
            if v_id == variant_id:
                popularity_rank = idx
                break
        
        # Get price history
        price_history_query = select(VariantPriceHistory).where(
            and_(
                VariantPriceHistory.variant_id == variant_id,
                VariantPriceHistory.effective_date >= start_date,
                VariantPriceHistory.effective_date <= end_date
            )
        ).order_by(VariantPriceHistory.effective_date.desc())
        
        price_history_result = await self.db.execute(price_history_query)
        price_history = [entry.to_dict() for entry in price_history_result.scalars().all()]
        
        # Get substitution suggestions
        substitution_suggestions = await self.suggest_variant_substitutions(variant_id)
        
        return {
            "variant_id": str(variant_id),
            "variant_name": variant.name,
            "product_name": variant.product.name if variant.product else None,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "period_type": period_type
            },
            "metrics": {
                "total_subscriptions": total_subscriptions,
                "canceled_subscriptions": canceled_subscriptions,
                "active_subscriptions": active_subscriptions,
                "total_revenue": total_revenue,
                "churn_rate": round(churn_rate, 2),
                "popularity_rank": popularity_rank
            },
            "price_history": price_history,
            "substitution_suggestions": substitution_suggestions
        }

    async def handle_variant_price_change(
        self,
        variant_id: UUID,
        old_price: float,
        new_price: float,
        old_sale_price: Optional[float] = None,
        new_sale_price: Optional[float] = None,
        change_reason: Optional[str] = None,
        changed_by_user_id: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        """
        Handle variant price change with historical record maintenance.
        Requirements: 3.2
        """
        # Verify variant exists
        variant_query = select(ProductVariant).where(ProductVariant.id == variant_id)
        variant_result = await self.db.execute(variant_query)
        variant = variant_result.scalar_one_or_none()
        
        if not variant:
            raise APIException(status_code=404, message="Product variant not found")
        
        # Count affected subscriptions
        affected_subscriptions_query = select(func.count(Subscription.id)).where(
            and_(
                Subscription.variant_ids.contains([str(variant_id)]),
                Subscription.status.in_(["active", "paused"])
            )
        )
        affected_count_result = await self.db.execute(affected_subscriptions_query)
        affected_subscriptions_count = affected_count_result.scalar() or 0
        
        # Create price history record
        price_history = VariantPriceHistory(
            variant_id=variant_id,
            old_price=old_price,
            new_price=new_price,
            old_sale_price=old_sale_price,
            new_sale_price=new_sale_price,
            change_reason=change_reason,
            changed_by_user_id=changed_by_user_id,
            effective_date=datetime.utcnow(),
            affected_subscriptions_count=affected_subscriptions_count
        )
        
        self.db.add(price_history)
        await self.db.commit()
        await self.db.refresh(price_history)
        
        # Get affected subscriptions for impact analysis
        affected_subscriptions_query = select(Subscription).where(
            and_(
                Subscription.variant_ids.contains([str(variant_id)]),
                Subscription.status.in_(["active", "paused"])
            )
        )
        affected_subscriptions_result = await self.db.execute(affected_subscriptions_query)
        affected_subscriptions = affected_subscriptions_result.scalars().all()
        
        # Create impact analysis
        subscription_impacts = []
        for subscription in affected_subscriptions:
            # Calculate price impact
            price_difference = new_price - old_price
            sale_price_difference = 0
            if old_sale_price is not None and new_sale_price is not None:
                sale_price_difference = new_sale_price - old_sale_price
            
            impact = {
                "subscription_id": str(subscription.id),
                "user_id": str(subscription.user_id),
                "price_difference": price_difference,
                "sale_price_difference": sale_price_difference,
                "percentage_change": (price_difference / old_price * 100) if old_price > 0 else 0,
                "new_total_impact": price_difference  # Simplified - would need full cost recalculation
            }
            subscription_impacts.append(impact)
        
        return subscription_impacts

    async def suggest_variant_substitutions(
        self,
        unavailable_variant_id: UUID,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Suggest variant substitutions for similar products.
        Requirements: 3.6
        """
        # Get the unavailable variant
        variant_query = select(ProductVariant).options(
            joinedload(ProductVariant.product)
        ).where(ProductVariant.id == unavailable_variant_id)
        variant_result = await self.db.execute(variant_query)
        unavailable_variant = variant_result.scalar_one_or_none()
        
        if not unavailable_variant:
            raise APIException(status_code=404, message="Product variant not found")
        
        # Check existing substitution suggestions
        existing_substitutions_query = select(VariantSubstitution).options(
            joinedload(VariantSubstitution.substitute_variant).joinedload(ProductVariant.product)
        ).where(
            and_(
                VariantSubstitution.original_variant_id == unavailable_variant_id,
                VariantSubstitution.is_active == True
            )
        ).order_by(desc(VariantSubstitution.similarity_score))
        
        existing_result = await self.db.execute(existing_substitutions_query)
        existing_substitutions = existing_result.scalars().all()
        
        suggestions = []
        
        # Add existing substitutions
        for substitution in existing_substitutions[:limit]:
            substitute_variant = substitution.substitute_variant
            suggestions.append({
                "variant_id": str(substitute_variant.id),
                "variant_name": substitute_variant.name,
                "product_name": substitute_variant.product.name if substitute_variant.product else None,
                "current_price": substitute_variant.current_price,
                "similarity_score": substitution.similarity_score,
                "substitution_reason": substitution.substitution_reason,
                "acceptance_rate": substitution.acceptance_rate,
                "times_suggested": substitution.times_suggested,
                "is_existing_suggestion": True
            })
        
        # If we need more suggestions, find similar variants
        if len(suggestions) < limit:
            remaining_limit = limit - len(suggestions)
            
            # Find variants from the same product (different sizes/variations)
            same_product_query = select(ProductVariant).options(
                joinedload(ProductVariant.product)
            ).where(
                and_(
                    ProductVariant.product_id == unavailable_variant.product_id,
                    ProductVariant.id != unavailable_variant_id,
                    ProductVariant.is_active == True
                )
            ).limit(remaining_limit)
            
            same_product_result = await self.db.execute(same_product_query)
            same_product_variants = same_product_result.scalars().all()
            
            for variant in same_product_variants:
                # Calculate similarity score based on price and attributes
                price_similarity = 1.0 - abs(variant.current_price - unavailable_variant.current_price) / max(variant.current_price, unavailable_variant.current_price)
                
                # Attribute similarity (simplified)
                attribute_similarity = 0.8  # Default high similarity for same product
                if variant.attributes and unavailable_variant.attributes:
                    common_attrs = set(variant.attributes.keys()) & set(unavailable_variant.attributes.keys())
                    if common_attrs:
                        matching_values = sum(1 for attr in common_attrs if variant.attributes.get(attr) == unavailable_variant.attributes.get(attr))
                        attribute_similarity = matching_values / len(common_attrs)
                
                overall_similarity = (price_similarity + attribute_similarity) / 2
                
                suggestions.append({
                    "variant_id": str(variant.id),
                    "variant_name": variant.name,
                    "product_name": variant.product.name if variant.product else None,
                    "current_price": variant.current_price,
                    "similarity_score": round(overall_similarity, 2),
                    "substitution_reason": "same_product_variant",
                    "acceptance_rate": 0.0,
                    "times_suggested": 0,
                    "is_existing_suggestion": False
                })
            
            # If still need more, find variants from same category with similar price
            if len(suggestions) < limit:
                remaining_limit = limit - len(suggestions)
                
                category_variants_query = select(ProductVariant).options(
                    joinedload(ProductVariant.product)
                ).join(Product).where(
                    and_(
                        Product.category_id == unavailable_variant.product.category_id,
                        ProductVariant.id != unavailable_variant_id,
                        ProductVariant.is_active == True,
                        ProductVariant.base_price.between(
                            unavailable_variant.base_price * 0.7,
                            unavailable_variant.base_price * 1.3
                        )
                    )
                ).limit(remaining_limit)
                
                category_result = await self.db.execute(category_variants_query)
                category_variants = category_result.scalars().all()
                
                for variant in category_variants:
                    # Skip if already in suggestions
                    if any(s["variant_id"] == str(variant.id) for s in suggestions):
                        continue
                    
                    price_similarity = 1.0 - abs(variant.current_price - unavailable_variant.current_price) / max(variant.current_price, unavailable_variant.current_price)
                    overall_similarity = price_similarity * 0.6  # Lower similarity for different products
                    
                    suggestions.append({
                        "variant_id": str(variant.id),
                        "variant_name": variant.name,
                        "product_name": variant.product.name if variant.product else None,
                        "current_price": variant.current_price,
                        "similarity_score": round(overall_similarity, 2),
                        "substitution_reason": "similar_category_price",
                        "acceptance_rate": 0.0,
                        "times_suggested": 0,
                        "is_existing_suggestion": False
                    })
        
        # Sort by similarity score and return top suggestions
        suggestions.sort(key=lambda x: x["similarity_score"], reverse=True)
        return suggestions[:limit]

    async def record_substitution_suggestion(
        self,
        original_variant_id: UUID,
        substitute_variant_id: UUID,
        similarity_score: float,
        substitution_reason: str = "auto_generated"
    ) -> VariantSubstitution:
        """Record a substitution suggestion for tracking"""
        # Check if substitution already exists
        existing_query = select(VariantSubstitution).where(
            and_(
                VariantSubstitution.original_variant_id == original_variant_id,
                VariantSubstitution.substitute_variant_id == substitute_variant_id
            )
        )
        existing_result = await self.db.execute(existing_query)
        existing = existing_result.scalar_one_or_none()
        
        if existing:
            # Update existing suggestion
            existing.times_suggested += 1
            existing.similarity_score = similarity_score
            existing.substitution_reason = substitution_reason
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        else:
            # Create new substitution
            substitution = VariantSubstitution(
                original_variant_id=original_variant_id,
                substitute_variant_id=substitute_variant_id,
                similarity_score=similarity_score,
                substitution_reason=substitution_reason,
                times_suggested=1,
                times_accepted=0,
                acceptance_rate=0.0
            )
            
            self.db.add(substitution)
            await self.db.commit()
            await self.db.refresh(substitution)
            return substitution

    async def record_substitution_acceptance(
        self,
        original_variant_id: UUID,
        substitute_variant_id: UUID
    ) -> bool:
        """Record when a substitution suggestion is accepted"""
        substitution_query = select(VariantSubstitution).where(
            and_(
                VariantSubstitution.original_variant_id == original_variant_id,
                VariantSubstitution.substitute_variant_id == substitute_variant_id
            )
        )
        substitution_result = await self.db.execute(substitution_query)
        substitution = substitution_result.scalar_one_or_none()
        
        if substitution:
            substitution.times_accepted += 1
            substitution.acceptance_rate = (substitution.times_accepted / substitution.times_suggested) * 100
            await self.db.commit()
            return True
        
        return False

    async def get_variant_tracking_history(
        self,
        variant_id: UUID,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get tracking history for a variant"""
        tracking_query = select(VariantTrackingEntry).options(
            joinedload(VariantTrackingEntry.subscription)
        ).where(
            VariantTrackingEntry.variant_id == variant_id
        ).order_by(desc(VariantTrackingEntry.tracking_timestamp)).limit(limit)
        
        tracking_result = await self.db.execute(tracking_query)
        tracking_entries = tracking_result.scalars().all()
        
        return [entry.to_dict() for entry in tracking_entries]

    async def get_popular_variants(
        self,
        limit: int = 10,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get most popular variants based on subscription additions"""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        popularity_query = select(
            VariantTrackingEntry.variant_id,
            func.count(VariantTrackingEntry.id).label("subscription_count"),
            func.sum(VariantTrackingEntry.price_at_time).label("total_revenue")
        ).where(
            and_(
                VariantTrackingEntry.action_type == "added",
                VariantTrackingEntry.tracking_timestamp >= start_date
            )
        ).group_by(VariantTrackingEntry.variant_id).order_by(desc("subscription_count")).limit(limit)
        
        popularity_result = await self.db.execute(popularity_query)
        popularity_data = popularity_result.all()
        
        popular_variants = []
        for variant_id, subscription_count, total_revenue in popularity_data:
            # Get variant details
            variant_query = select(ProductVariant).options(
                joinedload(ProductVariant.product)
            ).where(ProductVariant.id == variant_id)
            variant_result = await self.db.execute(variant_query)
            variant = variant_result.scalar_one_or_none()
            
            if variant:
                popular_variants.append({
                    "variant_id": str(variant_id),
                    "variant_name": variant.name,
                    "product_name": variant.product.name if variant.product else None,
                    "subscription_count": subscription_count,
                    "total_revenue": float(total_revenue or 0),
                    "current_price": variant.current_price
                })
        
        return popular_variants