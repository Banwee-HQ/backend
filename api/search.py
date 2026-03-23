from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, Dict, Any
from uuid import UUID
from core.db import get_db
from core.utils.response import Response
from core.errors import APIException
from services.search import SearchService

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("/")
async def search_products(
    q: str = Query(..., min_length=2, description="Search query (minimum 2 characters)"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
    category_id: Optional[UUID] = Query(None, description="Filter by category ID"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price filter"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price filter"),
    db: AsyncSession = Depends(get_db)
):
    """
    Search for products with fuzzy matching and weighted ranking.
    """
    try:
        from services.products import ProductService
        product_service = ProductService(db)
        
        # Build filters
        filters = {}
        if category_id:
            filters["category_id"] = category_id
        if min_price is not None:
            filters["min_price"] = min_price
        if max_price is not None:
            filters["max_price"] = max_price
        
        products = await product_service.search_products(
            query=q,
            limit=limit,
            filters=filters if filters else None
        )
        
        return Response.success(
            data={
                "query": q,
                "filters": filters,
                "products": products,
                "count": len(products)
            }
        )
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to search products: {str(e)}"
        )


@router.get("/autocomplete")
async def autocomplete_search(
    q: str = Query(..., min_length=2, description="Search query (minimum 2 characters)"),
    type: str = Query("product", regex="^(product|user|category)$", description="Search type: product, user, or category"),
    limit: int = Query(10, ge=1, le=20, description="Maximum number of suggestions"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get autocomplete suggestions for search queries.
    
    - **q**: Search query string (minimum 2 characters)
    - **type**: Type of search - "product", "user", or "category"
    - **limit**: Maximum number of suggestions (1-20, default 10)
    
    Returns suggestions with relevance scores for the specified type.
    """
    try:
        search_service = SearchService(db)
        suggestions = await search_service.autocomplete(
            query=q,
            search_type=type,
            limit=limit
        )
        
        return Response.success(
            data={
                "query": q,
                "type": type,
                "suggestions": suggestions,
                "count": len(suggestions)
            }
        )
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch autocomplete suggestions: {str(e)}"
        )