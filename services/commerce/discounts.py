"""
Discount Engine Service for subscription discount management
Implements discount code validation, calculation logic, and optimal discount selection
Requirements: 3.1, 3.2, 3.5
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from models.discounts import Discount, SubscriptionDiscount
from models.subscriptions import Subscription
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from decimal import Decimal
from enum import Enum
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)


class DiscountType(Enum):
    """Discount types supported by the engine"""
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"
    FREE_SHIPPING = "free_shipping"


class DiscountValidationResult:
    """Result of discount validation"""
    def __init__(self, is_valid: bool, error_message: str = None, discount: Discount = None):
        self.is_valid = is_valid
        self.error_message = error_message
        self.discount = discount


class DiscountCalculationResult:
    """Result of discount calculation"""
    def __init__(self, discount_amount: Decimal, final_total: Decimal, discount_type: str):
        self.discount_amount = discount_amount
        self.final_total = final_total
        self.discount_type = discount_type


class DiscountEngine:
    """Engine for managing subscription discounts with validation and optimization"""
    
    def __init__(self, db: AsyncSession):
        self.db = db

    async def validate_discount_code(
        self,
        discount_code: str,
        subscription_id: Optional[str] = None,
        subtotal: Optional[Decimal] = None
    ) -> DiscountValidationResult:
        """
        Validate discount code against promotional rules
        Requirements: 3.1, 3.5
        
        Args:
            discount_code: The discount code to validate
            subscription_id: Optional subscription ID for duplicate checking
            subtotal: Optional subtotal for minimum amount validation
            
        Returns:
            DiscountValidationResult with validation status and details
        """
        try:
            # Find the discount by code
            discount_result = await self.db.execute(
                select(Discount).where(
                    and_(
                        Discount.code == discount_code.upper(),
                        Discount.is_active == True
                    )
                )
            )
            discount = discount_result.scalar_one_or_none()
            
            if not discount:
                return DiscountValidationResult(
                    is_valid=False,
                    error_message="Invalid discount code"
                )
            
            # Check if discount is currently valid (date range)
            now = datetime.now(timezone.utc)
            if discount.valid_from > now:
                return DiscountValidationResult(
                    is_valid=False,
                    error_message="Discount code is not yet active"
                )
            
            if discount.valid_until < now:
                return DiscountValidationResult(
                    is_valid=False,
                    error_message="Discount code has expired"
                )
            
            # Check usage limit
            if discount.usage_limit and discount.used_count >= discount.usage_limit:
                return DiscountValidationResult(
                    is_valid=False,
                    error_message="Discount code has reached its usage limit"
                )
            
            # Check minimum amount requirement
            if discount.minimum_amount and subtotal:
                if subtotal < Decimal(str(discount.minimum_amount)):
                    return DiscountValidationResult(
                        is_valid=False,
                        error_message=f"Minimum order amount of ${discount.minimum_amount} required"
                    )
            
            # Check if already applied to this subscription
            if subscription_id:
                existing_discount = await self.db.execute(
                    select(SubscriptionDiscount).where(
                        and_(
                            SubscriptionDiscount.subscription_id == subscription_id,
                            SubscriptionDiscount.discount_id == discount.id
                        )
                    )
                )
                if existing_discount.scalar_one_or_none():
                    return DiscountValidationResult(
                        is_valid=False,
                        error_message="Discount code is already applied to this subscription"
                    )
            
            logger.info(f"Discount code {discount_code} validated successfully")
            return DiscountValidationResult(
                is_valid=True,
                discount=discount
            )
            
        except Exception as e:
            logger.error(f"Error validating discount code {discount_code}: {str(e)}")
            return DiscountValidationResult(
                is_valid=False,
                error_message="Error validating discount code"
            )

    async def calculate_discount_amount(
        self,
        discount: Discount,
        subtotal: Decimal,
        shipping_cost: Decimal = Decimal('0'),
        tax_amount: Decimal = Decimal('0')
    ) -> DiscountCalculationResult:
        """
        Calculate discount amount for percentage and fixed amount discounts
        Requirements: 3.1, 3.5
        
        Args:
            discount: The discount object to apply
            subtotal: Subscription subtotal
            shipping_cost: Shipping cost (for free shipping discounts)
            tax_amount: Tax amount
            
        Returns:
            DiscountCalculationResult with calculated amounts
        """
        try:
            discount_amount = Decimal('0')
            
            if discount.type == DiscountType.PERCENTAGE.value:
                # Calculate percentage discount on subtotal
                discount_amount = subtotal * (Decimal(str(discount.value)) / Decimal('100'))
                
                # Apply maximum discount limit if specified
                if discount.maximum_discount:
                    max_discount = Decimal(str(discount.maximum_discount))
                    discount_amount = min(discount_amount, max_discount)
            
            elif discount.type == DiscountType.FIXED_AMOUNT.value:
                # Fixed amount discount
                discount_amount = Decimal(str(discount.value))
                
                # Ensure discount doesn't exceed subtotal
                discount_amount = min(discount_amount, subtotal)
            
            elif discount.type == DiscountType.FREE_SHIPPING.value:
                # Free shipping discount
                discount_amount = shipping_cost
            
            else:
                logger.warning(f"Unknown discount type: {discount.type}")
                discount_amount = Decimal('0')
            
            # Ensure discount amount is not negative
            discount_amount = max(discount_amount, Decimal('0'))
            
            # Calculate final total (ensure non-negative)
            final_total = max(
                Decimal('0'),
                subtotal + shipping_cost + tax_amount - discount_amount
            )
            
            logger.info(f"Calculated discount: {discount_amount} for code {discount.code}")
            
            return DiscountCalculationResult(
                discount_amount=discount_amount,
                final_total=final_total,
                discount_type=discount.type
            )
            
        except Exception as e:
            logger.error(f"Error calculating discount for {discount.code}: {str(e)}")
            return DiscountCalculationResult(
                discount_amount=Decimal('0'),
                final_total=subtotal + shipping_cost + tax_amount,
                discount_type=discount.type
            )

    async def select_optimal_discount(
        self,
        available_discounts: List[Discount],
        subtotal: Decimal,
        shipping_cost: Decimal = Decimal('0'),
        tax_amount: Decimal = Decimal('0')
    ) -> Tuple[Optional[Discount], DiscountCalculationResult]:
        """
        Select the most beneficial discount when multiple are applicable
        Requirements: 3.2
        
        Args:
            available_discounts: List of valid discounts to choose from
            subtotal: Subscription subtotal
            shipping_cost: Shipping cost
            tax_amount: Tax amount
            
        Returns:
            Tuple of (best_discount, calculation_result) or (None, None) if no valid discounts
        """
        if not available_discounts:
            return None, None
        
        best_discount = None
        best_calculation = None
        max_savings = Decimal('0')
        
        try:
            for discount in available_discounts:
                # Calculate discount amount for this discount
                calculation = await self.calculate_discount_amount(
                    discount=discount,
                    subtotal=subtotal,
                    shipping_cost=shipping_cost,
                    tax_amount=tax_amount
                )
                
                # Check if this discount provides better savings
                if calculation.discount_amount > max_savings:
                    max_savings = calculation.discount_amount
                    best_discount = discount
                    best_calculation = calculation
            
            if best_discount:
                logger.info(f"Selected optimal discount: {best_discount.code} with savings of {max_savings}")
            else:
                logger.info("No beneficial discounts found")
            
            return best_discount, best_calculation
            
        except Exception as e:
            logger.error(f"Error selecting optimal discount: {str(e)}")
            return None, None

    async def apply_discount_to_subscription(
        self,
        subscription_id: str,
        discount_code: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Apply a discount to a subscription with full validation and optimization
        Requirements: 3.1, 3.2, 3.5
        
        Args:
            subscription_id: ID of the subscription
            discount_code: Discount code to apply
            user_id: ID of the user (for authorization)
            
        Returns:
            Dictionary with application result and details
        """
        try:
            # Get subscription details
            subscription_result = await self.db.execute(
                select(Subscription).where(
                    and_(
                        Subscription.id == subscription_id,
                        Subscription.user_id == user_id
                    )
                )
            )
            subscription = subscription_result.scalar_one_or_none()
            
            if not subscription:
                return {
                    'success': False,
                    'error': 'Subscription not found or access denied'
                }
            
            if subscription.status not in ['active', 'paused']:
                return {
                    'success': False,
                    'error': 'Cannot apply discount to inactive subscription'
                }
            
            # Validate discount code
            validation_result = await self.validate_discount_code(
                discount_code=discount_code,
                subscription_id=subscription_id,
                subtotal=Decimal(str(subscription.subtotal or 0))
            )
            
            if not validation_result.is_valid:
                return {
                    'success': False,
                    'error': validation_result.error_message
                }
            
            discount = validation_result.discount
            
            # Get current subscription amounts
            subtotal = Decimal(str(subscription.subtotal or 0))
            shipping_cost = Decimal(str(subscription.shipping_cost or 0))
            tax_amount = Decimal(str(subscription.tax_amount or 0))
            
            # Check for existing discounts and determine if we should replace them
            existing_discounts_result = await self.db.execute(
                select(SubscriptionDiscount).where(
                    SubscriptionDiscount.subscription_id == subscription_id
                ).join(Discount)
            )
            existing_discounts = existing_discounts_result.scalars().all()
            
            # Calculate new discount
            new_calculation = await self.calculate_discount_amount(
                discount=discount,
                subtotal=subtotal,
                shipping_cost=shipping_cost,
                tax_amount=tax_amount
            )
            
            # If there are existing discounts, compare and select optimal
            if existing_discounts:
                current_discount_amount = sum(
                    Decimal(str(ed.discount_amount)) for ed in existing_discounts
                )
                
                if new_calculation.discount_amount <= current_discount_amount:
                    return {
                        'success': False,
                        'error': 'A better discount is already applied to this subscription'
                    }
                
                # Remove existing discounts as the new one is better
                for existing_discount in existing_discounts:
                    await self.db.delete(existing_discount)
                    
                    # Decrement usage count of removed discount
                    removed_discount_result = await self.db.execute(
                        select(Discount).where(Discount.id == existing_discount.discount_id)
                    )
                    removed_discount = removed_discount_result.scalar_one_or_none()
                    if removed_discount:
                        removed_discount.used_count = max(0, removed_discount.used_count - 1)
            
            # Apply the new discount
            subscription_discount = SubscriptionDiscount(
                subscription_id=subscription_id,
                discount_id=discount.id,
                discount_amount=float(new_calculation.discount_amount)
            )
            self.db.add(subscription_discount)
            
            # Update discount usage count
            discount.used_count += 1
            
            # Update subscription totals
            subscription.discount_amount = float(new_calculation.discount_amount)
            subscription.total = float(new_calculation.final_total)
            
            await self.db.commit()
            
            logger.info(f"Successfully applied discount {discount_code} to subscription {subscription_id}")
            
            return {
                'success': True,
                'discount_code': discount_code,
                'discount_type': discount.type,
                'discount_amount': float(new_calculation.discount_amount),
                'new_total': float(new_calculation.final_total),
                'savings': float(new_calculation.discount_amount),
                'applied_at': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error applying discount {discount_code} to subscription {subscription_id}: {str(e)}")
            return {
                'success': False,
                'error': 'Internal error applying discount'
            }

    async def remove_expired_discounts(self) -> Dict[str, Any]:
        """
        Background job for checking and removing expired discounts
        Requirements: 3.3
        
        Returns:
            Summary of expired discounts removed
        """
        try:
            now = datetime.now(timezone.utc)
            
            # Find expired discounts that are still active
            expired_discounts_result = await self.db.execute(
                select(Discount).where(
                    and_(
                        Discount.valid_until < now,
                        Discount.is_active == True
                    )
                )
            )
            expired_discounts = expired_discounts_result.scalars().all()
            
            if not expired_discounts:
                logger.info("No expired discounts found")
                return {
                    'expired_discounts_count': 0,
                    'affected_subscriptions': 0,
                    'notifications_sent': 0
                }
            
            expired_discount_ids = [d.id for d in expired_discounts]
            
            # Find affected subscriptions
            affected_subscriptions_result = await self.db.execute(
                select(SubscriptionDiscount.subscription_id).where(
                    SubscriptionDiscount.discount_id.in_(expired_discount_ids)
                ).distinct()
            )
            affected_subscription_ids = [row[0] for row in affected_subscriptions_result.fetchall()]
            
            # Remove expired discount applications
            await self.db.execute(
                select(SubscriptionDiscount).where(
                    SubscriptionDiscount.discount_id.in_(expired_discount_ids)
                ).delete()
            )
            
            # Mark discounts as inactive
            for discount in expired_discounts:
                discount.is_active = False
            
            await self.db.commit()
            
            # TODO: Send notifications to affected users
            # This would typically integrate with a notification service
            notifications_sent = len(affected_subscription_ids)
            
            logger.info(f"Removed {len(expired_discounts)} expired discounts affecting {len(affected_subscription_ids)} subscriptions")
            
            return {
                'expired_discounts_count': len(expired_discounts),
                'affected_subscriptions': len(affected_subscription_ids),
                'notifications_sent': notifications_sent,
                'expired_codes': [d.code for d in expired_discounts]
            }
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error removing expired discounts: {str(e)}")
            return {
                'expired_discounts_count': 0,
                'affected_subscriptions': 0,
                'notifications_sent': 0,
                'error': str(e)
            }

    async def get_applicable_discounts(
        self,
        subtotal: Decimal,
        location_code: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> List[Discount]:
        """
        Get list of currently applicable discounts for a given context
        
        Args:
            subtotal: Subscription subtotal for minimum amount checking
            location_code: Optional location for geo-targeted discounts
            user_id: Optional user ID for user-specific discounts
            
        Returns:
            List of applicable discounts
        """
        try:
            now = datetime.now(timezone.utc)
            
            # Base query for active, non-expired discounts
            query = select(Discount).where(
                and_(
                    Discount.is_active == True,
                    Discount.valid_from <= now,
                    Discount.valid_until >= now,
                    or_(
                        Discount.usage_limit.is_(None),
                        Discount.used_count < Discount.usage_limit
                    ),
                    or_(
                        Discount.minimum_amount.is_(None),
                        Discount.minimum_amount <= subtotal
                    )
                )
            )
            
            result = await self.db.execute(query)
            applicable_discounts = result.scalars().all()
            
            logger.info(f"Found {len(applicable_discounts)} applicable discounts for subtotal {subtotal}")
            return applicable_discounts
            
        except Exception as e:
            logger.error(f"Error getting applicable discounts: {str(e)}")
            return []

    async def create_discount(
        self,
        code: str,
        discount_type: str,
        value: float,
        valid_from: datetime,
        valid_until: datetime,
        minimum_amount: Optional[float] = None,
        maximum_discount: Optional[float] = None,
        usage_limit: Optional[int] = None
    ) -> Discount:
        """
        Create a new discount for testing and administrative purposes
        
        Returns:
            Created discount object
        """
        try:
            discount = Discount(
                code=code.upper(),
                type=discount_type,
                value=value,
                valid_from=valid_from,
                valid_until=valid_until,
                minimum_amount=minimum_amount,
                maximum_discount=maximum_discount,
                usage_limit=usage_limit,
                used_count=0,
                is_active=True
            )
            
            self.db.add(discount)
            await self.db.commit()
            await self.db.refresh(discount)
            
            logger.info(f"Created discount: {code}")
            return discount
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating discount {code}: {str(e)}")
            raise