from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID
from core.db import get_db
from core.utils.response import Response
from core.errors import APIException
from core.logging import get_logger
from schemas.product import ProductCreate, ProductUpdate
from services.products import ProductService
from services.search import SearchService
from models.user import User
from services.auth import AuthService
from fastapi.security import OAuth2PasswordBearer

logger = get_logger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def get_current_auth_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    auth_service = AuthService(db)
    return await auth_service.get_current_user(token)

router = APIRouter(prefix="/products", tags=["Products"])
# /products?sort_by=created_at&sort_order=desc&page=1&limit=12


@router.get("/search")
async def search_products(
    q: str = Query(..., min_length=2, description="Search query (minimum 2 characters)"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
    category_id: Optional[UUID] = Query(None, description="Filter by category ID"),
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


@router.get("/categories/search")
async def search_categories(
    q: str = Query(..., min_length=2, description="Search query (minimum 2 characters)"),
    limit: int = Query(20, ge=1, le=50, description="Maximum number of results"),
    db: AsyncSession = Depends(get_db)
):
    """
    Advanced search for categories with prefix matching and fuzzy search.
    """
    try:
        product_service = ProductService(db)
        
        categories = await product_service.search_categories(
            query=q,
            limit=limit
        )
        
        return Response.success(
            data={
                "query": q,
                "categories": categories,
                "count": len(categories)
            }
        )
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to search categories: {str(e)}"
        )


@router.get("/home")
async def get_home_data(
    db: AsyncSession = Depends(get_db)
):
    """Get all data needed for the home page in one request."""
    try:
        product_service = ProductService(db)
        
        # Fetch categories (limit to 10 for home page carousel)
        categories = await product_service.get_categories()
        
        # Fetch featured products (4 items)
        featured = await product_service.get_featured_products(limit=4)
        
        # Fetch popular/recent products (20 items for filtering by category)
        popular_result = await product_service.get_products(
            page=1,
            limit=20,
            filters={},
            sort_by="created_at",
            sort_order="desc"
        )
        
        # Fetch products on sale for deals section (10 items)
        deals_result = await product_service.get_products(
            page=1,
            limit=10,
            filters={"sale": True},
            sort_by="created_at",
            sort_order="desc"
        )

        # Fallbacks if featured/deals are empty
        if not featured:
            featured = (popular_result.get("data") or [])[:4]

        if not deals_result.get("data"):
            deals_result = await product_service.get_products(
                page=1,
                limit=10,
                filters={},
                sort_by="created_at",
                sort_order="desc"
            )
        
        return Response.success(
            data={
                "categories": categories[:10] if categories else [],  # Limit to 10 for home page
                "featured": featured,
                "popular": popular_result["data"],
                "deals": deals_result["data"]
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
    category: Optional[str] = None,
    q: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
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
            
            # Build search filters
            search_filters = {}
            if min_price is not None:
                search_filters["min_price"] = min_price
            if max_price is not None:
                search_filters["max_price"] = max_price
            
            # Get category ID if category name is provided
            if category:
                product_service = ProductService(db)
                categories = await product_service.get_categories()
                category_match = next((cat for cat in categories if cat.name.lower() == category.lower()), None)
                if category_match:
                    search_filters["category_id"] = category_match.id
            
            # Use advanced search
            search_results = await search_service.fuzzy_search_products(
                query=q.strip(),
                limit=limit,
                filters=search_filters if search_filters else None
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
                "category": category,
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

@router.get("/categories")
async def get_categories(
    q: Optional[str] = Query(None, description="Search query for category name"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of categories"),
    search_mode: Optional[str] = Query("basic", regex="^(basic|advanced)$", description="Search mode: basic or advanced"),
    db: AsyncSession = Depends(get_db)
):
    """Get product categories with optional search functionality."""
    try:
        # If there's a search query and advanced search is requested, use the search service
        if q and len(q.strip()) >= 2 and search_mode == "advanced":
            search_service = SearchService(db)
            
            # Use advanced search
            search_results = await search_service.search_categories(
                query=q.strip(),
                limit=limit
            )
            
            return Response.success( 
                data={
                    "categories": search_results,
                    "count": len(search_results),
                    "search_mode": "advanced"
                }
            )
        else:
            # Use basic product service for regular queries
            product_service = ProductService(db)
            categories = await product_service.get_categories()
            
            # Apply basic filtering if search query is provided
            if q and len(q.strip()) >= 2:
                query_lower = q.strip().lower()
                categories = [
                    cat for cat in categories 
                    if query_lower in cat.name.lower() or 
                       (cat.description and query_lower in cat.description.lower())
                ]
            
            # Apply limit
            categories = categories[:limit]
            
            return Response.success( 
                data={
                    "categories": categories,
                    "count": len(categories),
                    "search_mode": "basic"
                }
            )
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch categories {str(e)}"
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


@router.get("/variants/{variant_id}/qrcode")
async def get_variant_qrcode(
    variant_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get QR code for a product variant."""
    try:
        product_service = ProductService(db)
        qr_code_url = await product_service.generate_product_url_qr(variant_id)
        if not qr_code_url:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Product variant not found"
            )
        return Response.success(data={"qr_code_url": qr_code_url})
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to generate QR code - {str(e)}"
        )


@router.get("/suppliers/products")
async def get_supplier_products(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_auth_user)
):
    """Get supplier's own products"""
    try:
        # Check if user is a supplier or admin
        if current_user.role not in ["Supplier", "Admin"]:
            raise APIException(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Access denied. Supplier or Admin role required."
            )
        
        # Get products for this supplier
        products = await product_service.get_products(
            page=page,
            limit=limit,
            filters={"supplier_id": str(current_user.id)} if current_user.role == "Supplier" else {}
        )
        return Response.success(data=products)
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch supplier products: {str(e)}"
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


@router.get("/categories/{category_id}")
async def get_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific category by ID."""
    try:
        category_service = ProductService(db)
        category = await category_service.get_category_by_id(category_id)
        if not category:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Category not found"
            )
        return Response(success=True, data=category)
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to fetch category"
        )


@router.post("/")
async def create_product(
    product_data: ProductCreate,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new product (suppliers only)."""
    try:
        if current_user.role not in ["Supplier", "Admin"]:
            raise APIException(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Only suppliers can create products"
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
    """Update a product (suppliers only)."""
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
    """Delete a product (suppliers only)."""
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
