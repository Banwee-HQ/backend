"""
Tax calculation service
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from models.tax_rates import TaxRate
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)


class TaxService:
    """Service for tax rate lookups and calculations"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_tax_rate(
        self, 
        country_code: str, 
        province_code: Optional[str] = None
    ) -> float:
        """
        Get tax rate for a specific location
        
        Args:
            country_code: ISO 3166-1 alpha-2 country code (e.g., "US", "CA", "GB")
            province_code: State/Province code (e.g., "CA" for California, "ON" for Ontario)
        
        Returns:
            Tax rate as decimal (e.g., 0.0725 for 7.25%)
        """
        try:
            # First try to find province-specific tax rate
            if province_code:
                result = await self.db.execute(
                    select(TaxRate).where(
                        and_(
                            TaxRate.country_code == country_code.upper(),
                            TaxRate.province_code == province_code.upper(),
                            TaxRate.is_active == True
                        )
                    )
                )
                tax_rate = result.scalar_one_or_none()
                
                if tax_rate:
                    logger.info(f"Found tax rate for {country_code}-{province_code}: {tax_rate.tax_rate * 100}%")
                    return tax_rate.tax_rate
            
            # Fall back to country-level tax rate
            result = await self.db.execute(
                select(TaxRate).where(
                    and_(
                        TaxRate.country_code == country_code.upper(),
                        TaxRate.province_code.is_(None),
                        TaxRate.is_active == True
                    )
                )
            )
            tax_rate = result.scalar_one_or_none()
            
            if tax_rate:
                logger.info(f"Found country tax rate for {country_code}: {tax_rate.tax_rate * 100}%")
                return tax_rate.tax_rate
            
            # Default to 0% if no tax rate found
            logger.warning(f"No tax rate found for {country_code}-{province_code}, defaulting to 0%")
            return 0.0
            
        except Exception as e:
            logger.error(f"Error getting tax rate for {country_code}-{province_code}: {e}")
            return 0.0
    
    async def calculate_tax(
        self, 
        amount: float, 
        country_code: str, 
        province_code: Optional[str] = None
    ) -> float:
        """
        Calculate tax amount for a given subtotal
        
        Args:
            amount: Subtotal amount to calculate tax on
            country_code: ISO 3166-1 alpha-2 country code
            province_code: State/Province code (optional)
        
        Returns:
            Tax amount
        """
        logger.info(f"Calculating tax for amount ${amount:.2f}, country: {country_code}, province: {province_code}")
        tax_rate = await self.get_tax_rate(country_code, province_code)
        tax_amount = amount * tax_rate
        logger.info(f"Calculated tax: ${amount:.2f} × {tax_rate * 100}% = ${tax_amount:.2f}")
        return round(tax_amount, 2)
    
    async def get_tax_info(
        self, 
        country_code: str, 
        province_code: Optional[str] = None
    ) -> dict:
        """
        Get detailed tax information for a location
        
        Returns:
            Dictionary with tax rate, name, and location info
        """
        try:
            # Try province-specific first
            if province_code:
                result = await self.db.execute(
                    select(TaxRate).where(
                        and_(
                            TaxRate.country_code == country_code.upper(),
                            TaxRate.province_code == province_code.upper(),
                            TaxRate.is_active == True
                        )
                    )
                )
                tax_rate = result.scalar_one_or_none()
                
                if tax_rate:
                    return {
                        "country_code": tax_rate.country_code,
                        "country_name": tax_rate.country_name,
                        "province_code": tax_rate.province_code,
                        "province_name": tax_rate.province_name,
                        "tax_rate": tax_rate.tax_rate,
                        "tax_percentage": tax_rate.tax_rate * 100,
                        "tax_name": tax_rate.tax_name,
                    }
            
            # Fall back to country-level
            result = await self.db.execute(
                select(TaxRate).where(
                    and_(
                        TaxRate.country_code == country_code.upper(),
                        TaxRate.province_code.is_(None),
                        TaxRate.is_active == True
                    )
                )
            )
            tax_rate = result.scalar_one_or_none()
            
            if tax_rate:
                return {
                    "country_code": tax_rate.country_code,
                    "country_name": tax_rate.country_name,
                    "province_code": None,
                    "province_name": None,
                    "tax_rate": tax_rate.tax_rate,
                    "tax_percentage": tax_rate.tax_rate * 100,
                    "tax_name": tax_rate.tax_name,
                }
            
            # No tax rate found
            return {
                "country_code": country_code.upper(),
                "country_name": "Unknown",
                "province_code": province_code,
                "province_name": None,
                "tax_rate": 0.0,
                "tax_percentage": 0.0,
                "tax_name": "No Tax",
            }
            
        except Exception as e:
            logger.error(f"Error getting tax info: {e}")
            return {
                "country_code": country_code.upper(),
                "country_name": "Unknown",
                "province_code": province_code,
                "province_name": None,
                "tax_rate": 0.0,
                "tax_percentage": 0.0,
                "tax_name": "Error",
                "error": str(e)
            }
