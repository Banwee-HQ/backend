from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID
from core.db import get_db
from core.utils.response import Response
from core.exceptions import APIException
from core.logging import get_structured_logger as get_logger
from schemas.catalog.product import ProductCreate, ProductUpdate
from services.catalog.products import ProductService
from services.catalog.search import SearchService
from models.auth.user import User
from services.auth.auth import AuthService
from fastapi.security import OAuth2PasswordBearer

logger = get_logger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def get_current_auth_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    auth_service = AuthService(db)
    return await auth_service.get_current_user(token)

# Hardcoded categories since we moved to string-based system
CATEGORIES = [
    {"name": "Grains, Cereals & Beans", "slug": "grains-pulses"},
    {"name": "Fruits & Vegetables", "slug": "fruits-vegetables"},
    {"name": "Meat, Poultry & Seafood", "slug": "meat-seafood"},
    {"name": "Dairy, Eggs & Fats", "slug": "dairy-fats"},
    {"name": "Spices, Herbs & Seasonings", "slug": "spices-herbs"},
    {"name": "Pantry & Sweeteners", "slug": "pantry-sweeteners"},
    {"name": "Nuts, Seeds & Snacks", "slug": "nuts-seeds-snacks"},
    {"name": "Beverages, Tea & Coffee", "slug": "beverages"},
    {"name": "Bakery & Prepared Foods", "slug": "bakery"},
    {"name": "Fibers & Industrial Crops", "slug": "fibers"}
]

router = APIRouter(prefix="/products", tags=["Products"])
# /products?sort_by=created_at&sort_order=desc&page=1&limit=12


@router.get("/search")
async def search_products(
    q: str = Query(..., min_length=2, description="Search query (minimum 2 characters)"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price filter"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price filter"),
    db: AsyncSession = Depends(get_db)
):
    """
    Advanced search for products with fuzzy matching and weighted ranking.
    """
    try:
        product_service = ProductService(db)
        
        # Build filters
        filters = {}
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


@router.get("/home")
async def get_home_data(
    db: AsyncSession = Depends(get_db)
):
    """Get all data needed for the home page in one request."""
    try:
        product_service = ProductService(db)
        
        # Fetch featured products (4 items)
        featured = await product_service.get_featured_products(limit=4)
        
        # Fetch popular/recent products (20 items for filtering by category)
        try:
            popular_result = await product_service.get_products(
                page=1,
                limit=20,
                filters={},
                sort_by="created_at",
                sort_order="desc"
            )
            popular_products = popular_result.get("data", [])
        except Exception as e:
            logger.warning(f"Failed to fetch popular products: {e}")
            popular_products = []
        
        # Fetch products on sale for deals section (10 items)
        try:
            deals_result = await product_service.get_products(
                page=1,
                limit=10,
                filters={"sale": True},
                sort_by="created_at",
                sort_order="desc"
            )
            deals_products = deals_result.get("data", [])
        except Exception as e:
            logger.warning(f"Failed to fetch deals: {e}")
            deals_products = []

        # Fallbacks if featured/deals are empty
        if not featured:
            featured = popular_products[:4]

        if not deals_products:
            # Use recent products as deals fallback
            deals_products = popular_products[:10] if popular_products else featured[:10]
        
        return Response.success(
            data={
                "categories": CATEGORIES,
                "featured": featured,
                "popular": popular_products,
                "deals": deals_products
            }
        )
    except Exception as e:
        logger.exception("Error fetching home data")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch home data: {str(e)}"
        )


@router.get("/")
async def get_products(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    q: Optional[str] = Query(None, description="Search query for filtering"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price filter"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price filter"),
    min_rating: Optional[int] = Query(None, ge=1, le=5),
    max_rating: Optional[int] = Query(None, ge=1, le=5),
    sort_by: Optional[str] = Query("created_at"),
    sort_order: Optional[str] = Query("desc"),
    availability: Optional[bool] = None,
    featured: Optional[bool] = None,
    popular: Optional[bool] = None,
    sale: Optional[bool] = None,
    search_mode: Optional[str] = Query("basic", regex="^(basic|advanced)$", description="Search mode: basic or advanced"),
    db: AsyncSession = Depends(get_db)
):
    """Get products with optional filtering, pagination, and advanced search."""
    try:
        # If there's a search query and advanced search is requested, use the search service
        if q and len(q.strip()) >= 2 and search_mode == "advanced":
            search_service = SearchService(db)
            
            # Build filters
            filters = {}
            if q:
                filters["q"] = q
            if min_price is not None:
                filters["min_price"] = min_price
            if max_price is not None:
                filters["max_price"] = max_price
            
            # Use advanced search
            search_results = await search_service.fuzzy_search_products(
                query=q.strip(),
                limit=limit,
                filters=filters if filters else None
            )
            
            # Convert search results to match the expected format
            return Response.success( 
                data={
                    "data": search_results,
                    "total": len(search_results),
                    "page": page,
                    "per_page": limit,
                    "total_pages": 1,
                    "search_mode": "advanced"
                }
            )
        else:
            # Use basic product service for regular queries
            product_service = ProductService(db)

            filters = {
                "q": q,
                "min_price": min_price,
                "max_price": max_price,
                "min_rating": min_rating,
                "max_rating": max_rating,
                "availability": availability,
                "featured": featured,
                "popular": popular,
                "sale": sale
            }

            result = await product_service.get_products(
                page=page,
                limit=limit,
                filters=filters,
                sort_by=sort_by,
                sort_order=sort_order
            )
            
            result["search_mode"] = "basic"
            return Response.success(data=result)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch products {str(e)}"
        )

@router.get("/{product_id}/recommendations")
async def get_recommended_products(
    product_id: UUID,
    limit: int = Query(4, ge=1, le=20),
    db: AsyncSession = Depends(get_db)
):
    """Get recommended products based on a product."""
    try:
        product_service = ProductService(db)
        products = await product_service.get_recommended_products(product_id, limit)
        return Response.success(data=products)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch recommended products - {str(e)}"
        )


@router.get("/{product_id}/variants")
async def get_product_variants(
    product_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get all variants for a product."""
    try:
        product_service = ProductService(db)
        variants = await product_service.get_product_variants(product_id)
        return Response.success(data=variants)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch product variants - {str(e)}"
        )


@router.get("/variants/{variant_id}")
async def get_variant(
    variant_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific product variant by ID."""
    try:
        product_service = ProductService(db)
        variant = await product_service.get_variant_by_id(variant_id)
        if not variant:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Product variant not found"
            )
        return Response.success(data=variant)
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch product variant - {str(e)}"
        )




@router.get("/{product_id}")
async def get_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific product by ID."""
    try:
        logger.debug(f"Fetching product with ID: {product_id}")
        product_service = ProductService(db)
        product = await product_service.get_product_by_id(product_id)
        if not product:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Product not found"
            )
        logger.debug(f"Successfully fetched product: {product.name}")
        return Response(success=True, data=product)
    except APIException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching product {product_id}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch product: {str(e)}"
        )


@router.post("/")
async def create_product(
    product_data: ProductCreate,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new product (admin only)."""
    try:
        if current_user.role not in ["Admin"]:
            raise APIException(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Only admins can create products"
            )

        product_service = ProductService(db)
        product = await product_service.create_product(product_data, current_user.id)
        return Response(success=True, data=product, message="Product created successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to create product"
        )


@router.put("/{product_id}")
async def update_product(
    product_id: UUID,
    product_data: ProductUpdate,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a product (admin only)."""
    try:
        product_service = ProductService(db)
        product = await product_service.update_product(product_id, product_data, current_user.id)
        return Response(success=True, data=product, message="Product updated successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to update product"
        )


@router.delete("/{product_id}")
async def delete_product(
    product_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a product (admin only)."""
    try:
        product_service = ProductService(db)
        await product_service.delete_product(product_id, current_user.id)
        return Response(success=True, message="Product deleted successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to delete product"
        )
