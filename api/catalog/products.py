from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from core.db import get_db
from core.dependencies import get_current_auth_user, require_admin
from core.utils.response import Response
from core.exceptions import APIException
from core.logging import get_structured_logger as get_logger
from schemas.catalog.product import Create, Update, ImageCreate, ImageUpdate, VariantCreate as ProductVariantCreate, VariantUpdate as ProductVariantUpdate, ProductPatch, VariantStockUpdate, ProductModeration, ProductFeatureToggle
from services.catalog.products import ProductService
from models.accounts.user import UserRole, User

logger = get_logger(__name__)

router = APIRouter(prefix="/products", tags=["Products"])
# /products?sort_by=created_at&sort_order=desc&page=1&limit=12

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


@router.get("/home/")
async def get_home_data(
    db: AsyncSession = Depends(get_db)
):
    """Get all data needed for the home page in one request."""
    try:
        product_service = ProductService(db)
        
        # Fetch featured products (4 items)
        featured = await product_service.featured(limit=4)
        
        # Fetch popular/recent products (8 items)
        try:
            popular_result = await product_service.list(
                page=1,
                limit=8,
                filters={},
                sort_by="created_at",
                sort_order="desc"
            )
            popular_products = popular_result.get("data", [])
        except Exception as e:
            logger.warning(f"Failed to fetch popular products: {e}")
            popular_products = []
        
        # Fetch products on sale for deals section (4 items)
        try:
            deals_result = await product_service.list(
                page=1,
                limit=4,
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
            deals_products = popular_products[:4] if popular_products else featured[:4]
        
        return Response.success(
            data={
                "categories": CATEGORIES,
                "featured": featured,
                "popular": popular_products,
                "deals": deals_products
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching home data")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch home data: {str(e)}"
        )


@router.get("/")
async def list(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=1000),
    category: Optional[str] = Query(None, description="category of the products"),
    q: Optional[str] = Query(None, description="Search query for filtering"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price filter"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price filter"),
    min_rating: Optional[int] = Query(None, ge=1, le=5),
    max_rating: Optional[int] = Query(None, ge=1, le=5),
    sort_by: Optional[str] = Query("created_at"),
    sort_order: Optional[str] = Query("desc"),
    availability: Optional[bool] = None,
    featured: Optional[bool] = None,
    is_featured: Optional[bool] = None,
    is_bestseller: Optional[bool] = None,
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
            "category":category,
            "min_price": min_price,
            "max_price": max_price,
            "min_rating": min_rating,
            "max_rating": max_rating,
            "availability": availability,
            "featured": featured,
            "is_featured": is_featured,
            "is_bestseller": is_bestseller,
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
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch products {str(e)}"
        )


@router.get("/featured/")
async def get_featured(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    """Get featured products."""
    try:
        product_service = ProductService(db)
        products = await product_service.featured(limit=limit)
        return Response.success(data=products)
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch featured products: {str(e)}"
        )


@router.get("/deals/")
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
        pagination = {
            "page": result.get("page", page),
            "limit": result.get("per_page", result.get("limit", limit)),
            "total": result.get("total", 0),
            "pages": result.get("total_pages", 1)
        }
        return Response.success(data=result.get("data", result), pagination=pagination)
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch deals: {str(e)}"
        )


@router.get("/{product_id}/recommendations/")
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
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch recommended products - {str(e)}"
        )


@router.get("/{product_id}/variants/")
async def variants(
    product_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get all variants for a product."""
    try:
        product_service = ProductService(db)
        variants = await product_service.list_variants(product_id)
        return Response.success(data=variants)
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch product variants - {str(e)}"
        )


@router.get("/variants/{variant_id}/")
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
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch product variant - {str(e)}"
        )

@router.get("/{product_id}/")
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
            product = await product_service.get(slug=product_id)
        if not product:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Product not found"
            )
        logger.debug(f"Successfully fetched product")
        return Response.success(data=product)
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching product {product_id}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch product: {str(e)}"
        )


@router.post("/")
async def create(
    product_data: Create,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new product (admin only)."""
    try:
        product_service = ProductService(db)
        product = await product_service.create(product_data, current_user.id)
        return Response.success(data=product, message="Product created successfully")
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to create product"
        )


@router.patch("/{product_id}/")
async def update(
    product_id: UUID,
    product_data: Update,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a product (admin only)."""
    try:
        product_service = ProductService(db)
        product = await product_service.update(product_id, product_data, current_user.id, is_admin=True)
        return Response.success(data=product, message="Product updated successfully")
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to update product"
        )


@router.delete("/{product_id}/")
async def delete(
    product_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a product (admin only)."""
    try:
        product_service = ProductService(db)
        await product_service.delete(product_id, current_user.id)
        return Response.success(message="Product deleted successfully")
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to delete product"
        )


# ==========================================================
# VARIANTS - 5 Standard APIs
# ==========================================================
@router.post("/{product_id}/variants/")
async def create_variant(
    product_id: UUID,
    variant_data: ProductVariantCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new variant for a product (admin only)."""
    try:
        product_service = ProductService(db)
        variant = await product_service.create_variant(product_id, variant_data)
        return Response.success(data=variant, message="Variant created successfully", code=status.HTTP_201_CREATED)
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to create variant: {str(e)}")


@router.get("/variants/{variant_id}/")
async def get_variant(
    variant_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific variant by ID."""
    try:
        product_service = ProductService(db)
        variant = await product_service.get_variant(variant_id)
        if not variant:
            raise APIException(status_code=404, message="Variant not found")
        return Response.success(data=variant)
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to fetch variant: {str(e)}")


@router.get("/{product_id}/variants/")
async def list_variants(
    product_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """List all variants for a product."""
    try:
        product_service = ProductService(db)
        variants = await product_service.list_variants(product_id)
        return Response.success(data=variants)
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to fetch variants: {str(e)}")


@router.patch("/variants/{variant_id}/")
async def patch_variant(
    variant_id: UUID,
    variant_data: ProductVariantUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a variant (admin only)."""
    try:
        product_service = ProductService(db)
        variant = await product_service.update_variant(variant_id, variant_data)
        return Response.success(data=variant, message="Variant updated successfully")
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to update variant: {str(e)}")


@router.delete("/variants/{variant_id}/")
async def delete_variant(
    variant_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a variant (admin only)."""
    try:
        product_service = ProductService(db)
        deleted = await product_service.delete_variant(variant_id)
        if not deleted:
            raise APIException(status_code=404, message="Variant not found")
        return Response.success(message="Variant deleted successfully")
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to delete variant: {str(e)}")


# ==========================================================
# VARIANT IMAGES - 5 Standard APIs
# ==========================================================
@router.post("/variants/{variant_id}/images/")
async def create_image(
    variant_id: UUID,
    image_data: ImageCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new image for a variant (admin only)."""
    try:
        product_service = ProductService(db)
        image = await product_service.create_image(
            variant_id=variant_id,
            url=image_data.url,
            alt_text=image_data.alt_text,
            is_primary=image_data.is_primary,
            sort_order=image_data.sort_order
        )
        return Response.success(data=image, message="Image created successfully", code=status.HTTP_201_CREATED)
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to create image: {str(e)}")


@router.get("/images/{image_id}/")
async def get_image(
    image_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific image by ID."""
    try:
        product_service = ProductService(db)
        image = await product_service.get_image(image_id)
        if not image:
            raise APIException(status_code=404, message="Image not found")
        return Response.success(data=image)
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to fetch image: {str(e)}")


@router.get("/variants/{variant_id}/images/")
async def list_images(
    variant_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """List all images for a variant."""
    try:
        product_service = ProductService(db)
        images = await product_service.list_images(variant_id)
        return Response.success(data=images)
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to fetch images: {str(e)}")


@router.patch("/images/{image_id}/")
async def patch_image(
    image_id: UUID,
    image_data: ImageUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update an image (admin only)."""
    try:
        product_service = ProductService(db)
        image = await product_service.update_image(
            image_id=image_id,
            url=image_data.url,
            alt_text=image_data.alt_text,
            is_primary=image_data.is_primary,
            sort_order=image_data.sort_order
        )
        if not image:
            raise APIException(status_code=404, message="Image not found")
        return Response.success(data=image, message="Image updated successfully")
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to update image: {str(e)}")


@router.delete("/images/{image_id}/")
async def delete_image(
    image_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete an image (admin only)."""
    try:
        product_service = ProductService(db)
        deleted = await product_service.delete_image(image_id)
        if not deleted:
            raise APIException(status_code=404, message="Image not found")
        return Response.success(message="Image deleted successfully")
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to delete image: {str(e)}")


@router.patch("/{product_id}/moderate/")
async def moderate(
    product_id: UUID,
    request: dict,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Moderate product (admin only)."""
    try:
        product_service = ProductService(db)
        result = await product_service.moderate(product_id, request.get("status"), request.get("notes"))
        return Response.success(data=result, message="Product moderated successfully")
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to moderate product: {str(e)}")


@router.patch("/{product_id}/feature/")
async def feature(
    product_id: UUID,
    featured: bool = True,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Feature/unfeature product (admin only)."""
    try:
        product_service = ProductService(db)
        result = await product_service.set_featured(product_id, featured)
        return Response.success(data=result, message="Product featured status updated")
    except APIException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to update featured status: {str(e)}")
