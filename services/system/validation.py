"""
Validation Service for tax and shipping amount validation with fallback rates
Implements validate_tax_amount, validate_shipping_amount, and apply_fallback_rates methods
Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from models.validation_rules import TaxValidationRule, ShippingValidationRule
from models.subscriptions import SubscriptionProduct
from models.product import Product
from decimal import Decimal
from typing import List, Dict, Any, Optional
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)


class ValidationService:
    """Service for validating tax and shipping amounts with fallback mechanisms"""
    
    def __init__(self, db: AsyncSession):
        self.db = db

    async def validate_tax_amount(
        self,
        amount: Decimal,
        location_code: str,
        subtotal: Optional[Decimal] = None
    ) -> Decimal:
        """
        Validate tax amount and apply fallback rates if necessary
        Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
        
        Args:
            amount: The calculated tax amount to validate
            location_code: Location code for tax rules (e.g., "US-CA", "GB")
            subtotal: Optional subtotal for recalculation if needed
            
        Returns:
            Validated tax amount (original or fallback)
        """
        # If amount is already non-zero and reasonable, return it
        if amount > 0:
            logger.debug(f"Tax amount {amount} is valid for location {location_code}")
            return amount
        
        # Amount is zero or negative, need to apply fallback
        logger.warning(f"Tax amount {amount} is invalid for location {location_code}, applying fallback")
        
        # Look for tax validation rule
        tax_rule_result = await self.db.execute(
            select(TaxValidationRule).where(
                and_(
                    TaxValidationRule.location_code == location_code,
                    TaxValidationRule.is_active == True
                )
            ).limit(1)
        )
        tax_rule = tax_rule_result.scalar_one_or_none()
        
        if tax_rule:
            if subtotal and subtotal > 0:
                # Recalculate tax using the rule
                fallback_amount = Decimal(str(tax_rule.calculate_tax(float(subtotal))))
                logger.info(f"Applied tax rule for {location_code}: {fallback_amount} (rate: {tax_rule.tax_rate})")
            else:
                # Use minimum tax
                fallback_amount = Decimal(str(tax_rule.minimum_tax))
                logger.info(f"Applied minimum tax for {location_code}: {fallback_amount}")
            
            return fallback_amount
        
        # No specific rule found, use default fallback
        default_fallback = await self._get_default_tax_fallback(location_code)
        logger.warning(f"No tax rule found for {location_code}, using default fallback: {default_fallback}")
        
        return default_fallback

    async def validate_shipping_amount(
        self,
        amount: Decimal,
        products: List[SubscriptionProduct],
        location_code: Optional[str] = None
    ) -> Decimal:
        """
        Validate shipping amount and apply fallback rates if necessary
        Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
        
        Args:
            amount: The calculated shipping amount to validate
            products: List of products for weight/shipping calculation
            location_code: Optional location code for shipping rules
            
        Returns:
            Validated shipping amount (original or fallback)
        """
        # If amount is already non-zero and reasonable, return it
        if amount > 0:
            logger.debug(f"Shipping amount {amount} is valid")
            return amount
        
        # Amount is zero or negative, need to apply fallback
        logger.warning(f"Shipping amount {amount} is invalid, applying fallback")
        
        # Calculate total weight (simplified estimation)
        total_weight = await self._calculate_total_weight(products)
        
        # Use location code or default
        location = location_code or "US"  # Default to US
        
        # Look for shipping validation rule
        shipping_rule_result = await self.db.execute(
            select(ShippingValidationRule).where(
                and_(
                    ShippingValidationRule.location_code == location,
                    ShippingValidationRule.weight_min <= total_weight,
                    ShippingValidationRule.weight_max >= total_weight,
                    ShippingValidationRule.is_active == True
                )
            ).limit(1)
        )
        shipping_rule = shipping_rule_result.scalar_one_or_none()
        
        if shipping_rule:
            fallback_amount = Decimal(str(shipping_rule.calculate_shipping(total_weight)))
            logger.info(f"Applied shipping rule for {location}: {fallback_amount} (weight: {total_weight}kg)")
            return fallback_amount
        
        # No specific rule found, use default fallback
        default_fallback = await self._get_default_shipping_fallback(total_weight, location)
        logger.warning(f"No shipping rule found for {location}, using default fallback: {default_fallback}")
        
        return default_fallback

    async def apply_fallback_rates(
        self,
        calculation_type: str,
        context: Dict[str, Any]
    ) -> Decimal:
        """
        Apply appropriate fallback rates for error recovery
        Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
        
        Args:
            calculation_type: Type of calculation ("tax" or "shipping")
            context: Context information for fallback calculation
            
        Returns:
            Fallback amount
        """
        if calculation_type.lower() == "tax":
            return await self._apply_tax_fallback(context)
        elif calculation_type.lower() == "shipping":
            return await self._apply_shipping_fallback(context)
        else:
            logger.error(f"Unknown calculation type: {calculation_type}")
            return Decimal('0.01')  # Minimal fallback

    async def _apply_tax_fallback(self, context: Dict[str, Any]) -> Decimal:
        """Apply tax fallback rates"""
        location_code = context.get('location_code', 'US')
        subtotal = context.get('subtotal', 0)
        
        if subtotal:
            subtotal_decimal = Decimal(str(subtotal))
        else:
            subtotal_decimal = None
        
        return await self.validate_tax_amount(
            amount=Decimal('0'),
            location_code=location_code,
            subtotal=subtotal_decimal
        )

    async def _apply_shipping_fallback(self, context: Dict[str, Any]) -> Decimal:
        """Apply shipping fallback rates"""
        products = context.get('products', [])
        location_code = context.get('location_code', 'US')
        
        return await self.validate_shipping_amount(
            amount=Decimal('0'),
            products=products,
            location_code=location_code
        )

    async def _calculate_total_weight(self, products: List[SubscriptionProduct]) -> float:
        """Calculate total weight of products (simplified estimation)"""
        if not products:
            return 0.5  # Default minimum weight
        
        # Simple estimation: 0.5kg per product
        # In a real system, this would query product weights from the database
        total_weight = len(products) * 0.5
        
        # Add some variation based on product quantities
        for product in products:
            if hasattr(product, 'quantity') and product.quantity:
                total_weight += (product.quantity - 1) * 0.3  # Additional weight per extra quantity
        
        return max(total_weight, 0.1)  # Minimum 0.1kg

    async def _get_default_tax_fallback(self, location_code: str) -> Decimal:
        """Get default tax fallback based on location"""
        # Default tax rates by region
        default_rates = {
            'US': 0.08,      # 8% average US sales tax
            'US-CA': 0.0875, # California sales tax
            'US-NY': 0.08,   # New York sales tax
            'US-TX': 0.0625, # Texas sales tax
            'GB': 0.20,      # UK VAT
            'DE': 0.19,      # German VAT
            'FR': 0.20,      # French VAT
            'CA': 0.13,      # Canadian HST/GST average
        }
        
        # Extract country code if location is country-state format
        country_code = location_code.split('-')[0] if '-' in location_code else location_code
        
        # Get rate for specific location or country, fallback to US rate
        rate = default_rates.get(location_code) or default_rates.get(country_code) or default_rates['US']
        
        # Return minimum tax amount (assuming small transaction)
        minimum_tax = Decimal('0.01')  # $0.01 minimum
        
        logger.info(f"Using default tax fallback for {location_code}: rate {rate}, minimum {minimum_tax}")
        return minimum_tax

    async def _get_default_shipping_fallback(self, weight: float, location_code: str) -> Decimal:
        """Get default shipping fallback based on weight and location"""
        # Default shipping rates by region (base rate + per kg)
        default_rates = {
            'US': {'base': 5.00, 'per_kg': 1.00},
            'GB': {'base': 4.50, 'per_kg': 0.80},
            'DE': {'base': 6.00, 'per_kg': 1.20},
            'FR': {'base': 5.50, 'per_kg': 1.10},
            'CA': {'base': 7.00, 'per_kg': 1.50},
        }
        
        # Extract country code if location is country-state format
        country_code = location_code.split('-')[0] if '-' in location_code else location_code
        
        # Get rates for country, fallback to US rates
        rates = default_rates.get(country_code) or default_rates['US']
        
        # Calculate shipping amount
        base_rate = rates['base']
        per_kg_rate = rates['per_kg']
        calculated_shipping = base_rate + (weight * per_kg_rate)
        
        # Ensure minimum shipping
        minimum_shipping = Decimal('2.00')  # $2.00 minimum
        fallback_amount = Decimal(str(max(calculated_shipping, float(minimum_shipping))))
        
        logger.info(f"Using default shipping fallback for {location_code}: {fallback_amount} (weight: {weight}kg)")
        return fallback_amount

    async def validate_subscription_amounts(
        self,
        subscription_id: str,
        tax_amount: Decimal,
        shipping_amount: Decimal,
        location_code: str,
        subtotal: Decimal,
        products: List[SubscriptionProduct]
    ) -> Dict[str, Any]:
        """
        Comprehensive validation of subscription amounts
        
        Returns:
            Dictionary with validated amounts and validation details
        """
        validation_result = {
            'subscription_id': subscription_id,
            'original_tax': float(tax_amount),
            'original_shipping': float(shipping_amount),
            'validated_tax': None,
            'validated_shipping': None,
            'tax_fallback_applied': False,
            'shipping_fallback_applied': False,
            'validation_errors': [],
            'validation_warnings': []
        }
        
        try:
            # Validate tax amount
            original_tax = tax_amount
            validated_tax = await self.validate_tax_amount(
                amount=tax_amount,
                location_code=location_code,
                subtotal=subtotal
            )
            
            validation_result['validated_tax'] = float(validated_tax)
            validation_result['tax_fallback_applied'] = validated_tax != original_tax
            
            if validation_result['tax_fallback_applied']:
                validation_result['validation_warnings'].append(
                    f"Tax fallback applied: {original_tax} -> {validated_tax}"
                )
            
            # Validate shipping amount
            original_shipping = shipping_amount
            validated_shipping = await self.validate_shipping_amount(
                amount=shipping_amount,
                products=products,
                location_code=location_code
            )
            
            validation_result['validated_shipping'] = float(validated_shipping)
            validation_result['shipping_fallback_applied'] = validated_shipping != original_shipping
            
            if validation_result['shipping_fallback_applied']:
                validation_result['validation_warnings'].append(
                    f"Shipping fallback applied: {original_shipping} -> {validated_shipping}"
                )
            
            logger.info(f"Validation completed for subscription {subscription_id}")
            
        except Exception as e:
            error_msg = f"Validation error for subscription {subscription_id}: {str(e)}"
            logger.error(error_msg)
            validation_result['validation_errors'].append(error_msg)
            
            # Provide safe fallback values
            if validation_result['validated_tax'] is None:
                validation_result['validated_tax'] = 0.01
            if validation_result['validated_shipping'] is None:
                validation_result['validated_shipping'] = 2.00
        
        return validation_result

    async def create_validation_rules(
        self,
        tax_rules: List[Dict[str, Any]] = None,
        shipping_rules: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create default validation rules for testing and initial setup
        
        Returns:
            Summary of created rules
        """
        created_rules = {
            'tax_rules': 0,
            'shipping_rules': 0,
            'errors': []
        }
        
        try:
            # Create default tax rules if none provided
            if tax_rules is None:
                tax_rules = [
                    {
                        'location_code': 'US',
                        'tax_rate': 0.08,
                        'minimum_tax': 0.01,
                        'description': 'Default US tax rate'
                    },
                    {
                        'location_code': 'US-CA',
                        'tax_rate': 0.0875,
                        'minimum_tax': 0.01,
                        'description': 'California sales tax'
                    },
                    {
                        'location_code': 'GB',
                        'tax_rate': 0.20,
                        'minimum_tax': 0.01,
                        'description': 'UK VAT'
                    }
                ]
            
            # Create tax rules
            for rule_data in tax_rules:
                # Check if rule already exists
                existing_rule = await self.db.execute(
                    select(TaxValidationRule).where(
                        TaxValidationRule.location_code == rule_data['location_code']
                    )
                )
                if existing_rule.scalar_one_or_none():
                    continue  # Skip if already exists
                
                tax_rule = TaxValidationRule(**rule_data)
                self.db.add(tax_rule)
                created_rules['tax_rules'] += 1
            
            # Create default shipping rules if none provided
            if shipping_rules is None:
                shipping_rules = [
                    {
                        'location_code': 'US',
                        'weight_min': 0.0,
                        'weight_max': 10.0,
                        'base_rate': 5.00,
                        'minimum_shipping': 2.00,
                        'description': 'US standard shipping (0-10kg)'
                    },
                    {
                        'location_code': 'US',
                        'weight_min': 10.0,
                        'weight_max': 50.0,
                        'base_rate': 15.00,
                        'minimum_shipping': 10.00,
                        'description': 'US heavy shipping (10-50kg)'
                    },
                    {
                        'location_code': 'GB',
                        'weight_min': 0.0,
                        'weight_max': 10.0,
                        'base_rate': 4.50,
                        'minimum_shipping': 2.00,
                        'description': 'UK standard shipping (0-10kg)'
                    }
                ]
            
            # Create shipping rules
            for rule_data in shipping_rules:
                # Check if rule already exists
                existing_rule = await self.db.execute(
                    select(ShippingValidationRule).where(
                        and_(
                            ShippingValidationRule.location_code == rule_data['location_code'],
                            ShippingValidationRule.weight_min == rule_data['weight_min'],
                            ShippingValidationRule.weight_max == rule_data['weight_max']
                        )
                    )
                )
                if existing_rule.scalar_one_or_none():
                    continue  # Skip if already exists
                
                shipping_rule = ShippingValidationRule(**rule_data)
                self.db.add(shipping_rule)
                created_rules['shipping_rules'] += 1
            
            await self.db.commit()
            logger.info(f"Created validation rules: {created_rules}")
            
        except Exception as e:
            await self.db.rollback()
            error_msg = f"Error creating validation rules: {str(e)}"
            logger.error(error_msg)
            created_rules['errors'].append(error_msg)
        
        return created_rules