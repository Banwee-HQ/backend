"""
Tax calculation routes
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from typing import Optional, List
from uuid import UUID
from decimal import Decimal
from core.logging import get_logger

from core.db import get_db
from core.dependencies import get_current_user, require_admin
from core.errors import APIException
from core.utils.response import Response
from models.user import User
from models.tax_rates import TaxRate
from services.tax import TaxService
from schemas.tax import (
    Currency,
    TaxCalculationRequest,
    TaxCalculationResponse,
    TaxRateCreate,
    TaxRateUpdate,
    TaxRateResponse,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/tax", tags=["tax"])


@router.post("/calculate")
async def calculate_tax(
    request: TaxCalculationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Calculate tax amount based on subtotal, shipping, and location
    """
    try:
        logger.info(f"Calculating tax for request: subtotal={request.subtotal}, shipping={request.shipping}, country={request.country_code}")
        
        tax_service = TaxService(db)
        
        # Calculate tax amount
        tax_amount = await tax_service.calculate_tax(
            amount=request.subtotal + request.shipping,
            country_code=request.country_code or 'US',
            province_code=request.state_code
        )
        logger.info(f"Tax amount calculated: {tax_amount}")
        
        # Get tax rate for response
        tax_rate = await tax_service.get_tax_rate(
            country_code=request.country_code or 'US',
            province_code=request.state_code
        )
        
        # Get tax info
        tax_info = await tax_service.get_tax_info(
            country_code=request.country_code or 'US',
            province_code=request.state_code
        )
        
        response_data = {
            "tax_amount": float(tax_amount),
            "tax_rate": float(tax_rate),
            "tax_type": tax_info.get('tax_name', 'Tax'),
            "jurisdiction": f"{tax_info.get('province_name', tax_info.get('country_name', 'Unknown'))}",
            "currency": request.currency,
            "breakdown": []
        }
        
        return Response.success(data=response_data)
        
    except Exception as e:
        import traceback
        logger.error(f"Tax calculation error: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to calculate tax: {str(e)}"
        )


# ============================================================================
# ADMIN TAX RATES MANAGEMENT ROUTES
# ============================================================================


@router.get("/admin/tax-rates")
async def list_tax_rates(
    country_code: Optional[str] = Query(None, description="Filter by country code"),
    province_code: Optional[str] = Query(None, description="Filter by province code"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search in country/province names"),
    sort_by: Optional[str] = Query(None, regex="^(created_at|country_name|tax_rate|tax_name)$"),
    sort_order: Optional[str] = Query(None, regex="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """List all tax rates with filtering and pagination (Admin only)"""
    try:
        # Build query
        query = select(TaxRate)
        count_query = select(func.count(TaxRate.id))
        
        # Apply filters
        conditions = []
        if country_code:
            conditions.append(TaxRate.country_code == country_code.upper())
        if province_code:
            conditions.append(TaxRate.province_code == province_code.upper())
        if is_active is not None:
            conditions.append(TaxRate.is_active == is_active)
        if search:
            search_term = f"%{search}%"
            conditions.append(
                or_(
                    TaxRate.country_name.ilike(search_term),
                    TaxRate.province_name.ilike(search_term),
                    TaxRate.tax_name.ilike(search_term)
                )
            )
        
        if conditions:
            query = query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))
        
        # Add dynamic sorting
        sort_field = sort_by or "created_at"
        sort_dir = sort_order or "desc"
        
        if sort_field == "created_at":
            if sort_dir == "asc":
                query = query.order_by(TaxRate.created_at.asc())
            else:
                query = query.order_by(TaxRate.created_at.desc())
        elif sort_field == "country_name":
            if sort_dir == "asc":
                query = query.order_by(TaxRate.country_name.asc())
            else:
                query = query.order_by(TaxRate.country_name.desc())
        elif sort_field == "tax_rate":
            if sort_dir == "asc":
                query = query.order_by(TaxRate.tax_rate.asc())
            else:
                query = query.order_by(TaxRate.tax_rate.desc())
        elif sort_field == "tax_name":
            if sort_dir == "asc":
                query = query.order_by(TaxRate.tax_name.asc().nulls_last())
            else:
                query = query.order_by(TaxRate.tax_name.desc().nulls_last())
        else:
            # Default sorting
            query = query.order_by(TaxRate.country_name, TaxRate.province_name)
        
        # Apply pagination
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)
        
        # Execute queries
        result = await db.execute(query)
        tax_rates = result.scalars().all()
        
        total = await db.scalar(count_query) or 0
        pages = (total + per_page - 1) // per_page
        
        # Convert to response format
        response_data = []
        for rate in tax_rates:
            response_data.append(TaxRateResponse(
                id=rate.id,
                country_code=rate.country_code,
                country_name=rate.country_name,
                province_code=rate.province_code,
                province_name=rate.province_name,
                tax_rate=rate.tax_rate,
                tax_percentage=rate.tax_rate * 100,
                tax_name=rate.tax_name,
                is_active=rate.is_active,
                created_at=rate.created_at.isoformat(),
                updated_at=rate.updated_at.isoformat() if rate.updated_at else None
            ))
        
        return Response.success(data={
            "data": response_data,
            "pagination": {
                "page": page,
                "limit": per_page,
                "total": total,
                "pages": pages
            }
        })
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch tax rates: {str(e)}"
        )


@router.get("/admin/tax-rates/countries")
async def get_countries_with_tax_rates(
    db: AsyncSession = Depends(get_db)
):
    """Get list of countries that have tax rates configured"""
    try:
        result = await db.execute(
            select(
                TaxRate.country_code,
                TaxRate.country_name,
                func.count(TaxRate.id).label('rate_count')
            )
            .group_by(TaxRate.country_code, TaxRate.country_name)
            .order_by(TaxRate.country_name)
        )
        
        countries = []
        for row in result:
            countries.append({
                "country_code": row.country_code,
                "country_name": row.country_name,
                "rate_count": row.rate_count
            })
        
        return countries
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch countries: {str(e)}"
        )


@router.get("/admin/tax-rates/tax-types")
async def get_available_tax_types(
    db: AsyncSession = Depends(get_db)
):
    """Get list of all tax types currently in use"""
    try:
        result = await db.execute(
            select(TaxRate.tax_name, func.count(TaxRate.id).label('usage_count'))
            .where(TaxRate.tax_name.isnot(None))
            .group_by(TaxRate.tax_name)
            .order_by(func.count(TaxRate.id).desc(), TaxRate.tax_name)
        )
        
        tax_types = []
        for row in result:
            tax_types.append({
                "value": row.tax_name,
                "label": row.tax_name,
                "usage_count": row.usage_count
            })
        
        return tax_types
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch tax types: {str(e)}"
        )


@router.get("/admin/tax-rates/{tax_rate_id}", response_model=TaxRateResponse)
async def get_tax_rate(
    tax_rate_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific tax rate by ID (Admin only)"""
    try:
        result = await db.execute(
            select(TaxRate).where(TaxRate.id == tax_rate_id)
        )
        tax_rate = result.scalar_one_or_none()
        
        if not tax_rate:
            raise HTTPException(status_code=404, detail="Tax rate not found")
        
        return TaxRateResponse(
            id=tax_rate.id,
            country_code=tax_rate.country_code,
            country_name=tax_rate.country_name,
            province_code=tax_rate.province_code,
            province_name=tax_rate.province_name,
            tax_rate=tax_rate.tax_rate,
            tax_percentage=tax_rate.tax_rate * 100,
            tax_name=tax_rate.tax_name,
            is_active=tax_rate.is_active,
            created_at=tax_rate.created_at.isoformat(),
            updated_at=tax_rate.updated_at.isoformat() if tax_rate.updated_at else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get tax rate: {str(e)}"
        )


@router.post("/admin/tax-rates", response_model=TaxRateResponse, status_code=status.HTTP_201_CREATED)
async def create_tax_rate(
    data: TaxRateCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new tax rate (Admin only)"""
    try:
        # Check if tax rate already exists for this location
        existing_query = select(TaxRate).where(
            and_(
                TaxRate.country_code == data.country_code.upper(),
                TaxRate.province_code == (data.province_code.upper() if data.province_code else None)
            )
        )
        result = await db.execute(existing_query)
        existing = result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Tax rate already exists for {data.country_code}" + 
                        (f"-{data.province_code}" if data.province_code else "")
            )
        
        # Create new tax rate
        tax_rate = TaxRate(
            country_code=data.country_code.upper(),
            country_name=data.country_name,
            province_code=data.province_code.upper() if data.province_code else None,
            province_name=data.province_name,
            tax_rate=data.tax_rate,
            tax_name=data.tax_name,
            is_active=data.is_active
        )
        
        db.add(tax_rate)
        await db.commit()
        await db.refresh(tax_rate)
        
        return TaxRateResponse(
            id=tax_rate.id,
            country_code=tax_rate.country_code,
            country_name=tax_rate.country_name,
            province_code=tax_rate.province_code,
            province_name=tax_rate.province_name,
            tax_rate=tax_rate.tax_rate,
            tax_percentage=tax_rate.tax_rate * 100,
            tax_name=tax_rate.tax_name,
            is_active=tax_rate.is_active,
            created_at=tax_rate.created_at.isoformat(),
            updated_at=tax_rate.updated_at.isoformat() if tax_rate.updated_at else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create tax rate: {str(e)}"
        )


@router.put("/admin/tax-rates/{tax_rate_id}", response_model=TaxRateResponse)
async def update_tax_rate(
    tax_rate_id: UUID,
    data: TaxRateUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update an existing tax rate (Admin only)"""
    try:
        result = await db.execute(
            select(TaxRate).where(TaxRate.id == tax_rate_id)
        )
        tax_rate = result.scalar_one_or_none()
        
        if not tax_rate:
            raise HTTPException(status_code=404, detail="Tax rate not found")
        
        # Update fields
        if data.country_name is not None:
            tax_rate.country_name = data.country_name
        if data.province_name is not None:
            tax_rate.province_name = data.province_name
        if data.tax_rate is not None:
            tax_rate.tax_rate = data.tax_rate
        if data.tax_name is not None:
            tax_rate.tax_name = data.tax_name
        if data.is_active is not None:
            tax_rate.is_active = data.is_active
        
        await db.commit()
        await db.refresh(tax_rate)
        
        return TaxRateResponse(
            id=tax_rate.id,
            country_code=tax_rate.country_code,
            country_name=tax_rate.country_name,
            province_code=tax_rate.province_code,
            province_name=tax_rate.province_name,
            tax_rate=tax_rate.tax_rate,
            tax_percentage=tax_rate.tax_rate * 100,
            tax_name=tax_rate.tax_name,
            is_active=tax_rate.is_active,
            created_at=tax_rate.created_at.isoformat(),
            updated_at=tax_rate.updated_at.isoformat() if tax_rate.updated_at else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update tax rate: {str(e)}"
        )


@router.delete("/admin/tax-rates/{tax_rate_id}")
async def delete_tax_rate(
    tax_rate_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a tax rate (Admin only)"""
    try:
        result = await db.execute(
            select(TaxRate).where(TaxRate.id == tax_rate_id)
        )
        tax_rate = result.scalar_one_or_none()
        
        if not tax_rate:
            raise HTTPException(status_code=404, detail="Tax rate not found")
        
        await db.delete(tax_rate)
        await db.commit()
        
        return {"message": "Tax rate deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete tax rate: {str(e)}"
        )


@router.post("/admin/tax-rates/bulk-update")
async def bulk_update_tax_rates(
    updates: List[dict],
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Bulk update multiple tax rates (Admin only)"""
    try:
        updated_count = 0
        errors = []
        
        for update_data in updates:
            try:
                tax_rate_id = UUID(update_data.get("id"))
                result = await db.execute(
                    select(TaxRate).where(TaxRate.id == tax_rate_id)
                )
                tax_rate = result.scalar_one_or_none()
                
                if tax_rate:
                    if "tax_rate" in update_data:
                        tax_rate.tax_rate = float(update_data["tax_rate"])
                    if "is_active" in update_data:
                        tax_rate.is_active = bool(update_data["is_active"])
                    if "tax_name" in update_data:
                        tax_rate.tax_name = update_data["tax_name"]
                    
                    updated_count += 1
                else:
                    errors.append(f"Tax rate {tax_rate_id} not found")
                    
            except Exception as e:
                errors.append(f"Error updating {update_data.get('id')}: {str(e)}")
        
        await db.commit()
        
        return Response.success(
            data={
                "updated_count": updated_count,
                "errors": errors
            },
            message=f"Successfully updated {updated_count} tax rates"
        )
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to bulk update tax rates: {str(e)}"
        )