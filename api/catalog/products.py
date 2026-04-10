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
from models.accounts.user import User
from services.accounts.auth import AuthService
from fastapi.security import OAuth2PasswordBearer

logger = get_logger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def get_current_auth_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    auth_service = AuthService(db)
    return await auth_service.current_user(token)

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


@router.get("/home")
async def get_home_data(
    db: AsyncSession = Depends(get_db)
):
    """Get all data needed for the home page in one request."""
    try:
        product_service = ProductService(db)
        
        # Fetch featured products (4 items)
        featured = await product_service.featured(limit=4)
        
        # Fetch popular/recent products (20 items for filtering by category)
        try:
            popular_result = await product_service.list(
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
            deals_result = await product_service.list(
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
async def list(
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
    """Get products with optional filtering and pagination."""
    try:
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

        result = await product_service.list(
            page=page,
            limit=limit,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        # Format response with pagination at the correct level
        pagination = {
            "page": result["page"],
            "limit": result["per_page"],
            "total": result["total"],
            "pages": result["total_pages"]
        }
        return Response.success(
            data=result["data"],
            pagination=pagination
        )
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch products {str(e)}"
        )

@router.get("/search")
async def search_products(
    q: str = Query(..., min_length=1, description="Search query"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Search products by name, description, or tags."""
    try:
        product_service = ProductService(db)
        result = await product_service.list(
            page=page,
            limit=limit,
            filters={"q": q},
            sort_by="created_at",
            sort_order="desc"
        )
        return Response.success(data=result)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to search products: {str(e)}"
        )


@router.get("/categories")
async def get_categories(db: AsyncSession = Depends(get_db)):
    """Get all product categories."""
    return Response.success(data=CATEGORIES)


@router.get("/featured")
async def get_featured(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    """Get featured products."""
    try:
        product_service = ProductService(db)
        products = await product_service.featured(limit=limit)
        return Response.success(data=products)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch featured products: {str(e)}"
        )


@router.get("/deals")
async def get_deals(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Get products on sale/deals."""
    try:
        product_service = ProductService(db)
        result = await product_service.list(
            page=page,
            limit=limit,
            filters={"sale": True},
            sort_by="created_at",
            sort_order="desc"
        )
        return Response.success(data=result)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch deals: {str(e)}"
        )


@router.get("/{product_id}/recommendations")
async def recommended(
    product_id: UUID,
    limit: int = Query(4, ge=1, le=20),
    db: AsyncSession = Depends(get_db)
):
    """Get recommended products based on a product."""
    try:
        product_service = ProductService(db)
        products = await product_service.recommended(product_id, limit)
        return Response.success(data=products)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch recommended products - {str(e)}"
        )


@router.get("/{product_id}/variants")
async def variants(
    product_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get all variants for a product."""
    try:
        product_service = ProductService(db)
        variants = await product_service.variants(product_id)
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
        variant = await product_service.get_variant(variant_id)
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
    product_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific product by ID or slug."""
    try:
        logger.debug(f"Fetching product with ID/slug: {product_id}")
        product_service = ProductService(db)
        product = None
        # Try UUID first
        try:
            from uuid import UUID as _UUID
            uid = _UUID(product_id)
            product = await product_service.get(uid)
        except (ValueError, AttributeError):
            # Try slug
            product = await product_service.get_by_slug(product_id)
        if not product:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Product not found"
            )
        logger.debug(f"Successfully fetched product")
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
async def create(
    product_data: ProductCreate,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new product (admin only)."""
    try:
        from models.accounts.user import UserRole
        if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
            raise APIException(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Only admins can create products"
            )

        product_service = ProductService(db)
        product = await product_service.create(product_data, current_user.id)
        return Response(success=True, data=product, message="Product created successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to create product"
        )


@router.put("/{product_id}")
async def update(
    product_id: UUID,
    product_data: ProductUpdate,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a product (admin only)."""
    try:
        product_service = ProductService(db)
        product = await product_service.update(product_id, product_data, current_user.id)
        return Response(success=True, data=product, message="Product updated successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to update product"
        )


@router.delete("/{product_id}")
async def delete(
    product_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a product (admin only)."""
    try:
        product_service = ProductService(db)
        await product_service.delete(product_id, current_user.id)
        return Response(success=True, message="Product deleted successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to delete product"
        )
