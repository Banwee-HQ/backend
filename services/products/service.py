from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.orm import selectinload
from typing import Optional, List, Dict, Any
from fastapi import HTTPException
import uuid
from uuid import UUID
from core.utils.uuid_utils import uuid7
from models.product import Product, ProductVariant, Category, ProductImage
from models.inventories import Inventory
from models.cart import CartItem
from models.user import User
from models.review import Review
from models.wishlist import WishlistItem
from schemas.product import (
    ProductCreate, ProductUpdate, ProductResponse, ProductListResponse,
    ProductVariantResponse, CategoryResponse, SupplierResponse,
    ProductImageResponse, PriceRange
)
from core.errors import APIException
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)


class ProductService:
    def __init__(self, db: AsyncSession):
        self.db = db
        
        # Search configuration
        self.similarity_threshold = 0.3
        self.weights = {
            "exact": 1.0,
            "prefix": 0.8,
            "fuzzy": 0.5
        }
        self.product_field_weights = {
            "name": 1.0,
            "description": 0.6,
            "category": 0.4,
            "tags": 0.3
        }

    def _convert_image_to_response(self, image: ProductImage) -> ProductImageResponse:
        """Convert ProductImage model to response format."""
        return ProductImageResponse(
            id=image.id,
            variant_id=image.variant_id,
            url=image.url,
            alt_text=image.alt_text,
            is_primary=image.is_primary,
            sort_order=image.sort_order,
            format=image.format,
            created_at=image.created_at.isoformat() if image.created_at else ""
        )

    def _convert_variant_to_response(self, variant: ProductVariant) -> ProductVariantResponse:
        """Convert ProductVariant model to response format."""
        try:
            # Use the model's built-in to_dict method
            variant_dict = variant.to_dict(include_images=True)
            return ProductVariantResponse.model_validate(variant_dict)
        except Exception as e:
            print(f"Error converting variant {variant.id}: {e}")
            # Return minimal variant data
            return ProductVariantResponse(
                id=variant.id,
                product_id=variant.product_id,
                sku=getattr(variant, 'sku', ''),
                name=getattr(variant, 'name', ''),
                base_price=getattr(variant, 'base_price', 0.0),
                sale_price=getattr(variant, 'sale_price', None),
                current_price=getattr(variant, 'sale_price', None) or getattr(
                    variant, 'base_price', 0.0),
                discount_percentage=0,
                stock=getattr(variant.inventory, 'quantity_available', 0) if hasattr(variant, 'inventory') and variant.inventory else 0,
                attributes=getattr(variant, 'attributes', {}),
                is_active=getattr(variant, 'is_active', True),
                images=[],
                primary_image=None,
                created_at=variant.created_at.isoformat() if variant.created_at else "",
                updated_at=variant.updated_at.isoformat() if variant.updated_at else None
            )

    def _convert_product_to_response(self, product: Product, include_relationships: bool = True) -> ProductResponse:
        """Convert Product model to response format."""
        try:
            # Use the model's built-in to_dict method and then convert to response
            product_dict = product.to_dict(include_variants=True)

            # Convert category
            category = None
            if include_relationships and product.category:
                try:
                    category = CategoryResponse(
                        id=product.category.id,
                        name=product.category.name,
                        description=product.category.description,
                        image_url=product.category.image_url,
                        is_active=product.category.is_active,
                        created_at=product.category.created_at.isoformat(
                        ) if product.category.created_at else "",
                        updated_at=product.category.updated_at.isoformat(
                        ) if product.category.updated_at else None
                    )
                except Exception as e:
                    print(f"Error converting category: {e}")
                    category = None

            # Convert supplier
            supplier = None
            if include_relationships and product.supplier:
                try:
                    supplier = SupplierResponse(
                        id=product.supplier.id,
                        email=product.supplier.email,
                        firstname=product.supplier.firstname,
                        lastname=product.supplier.lastname,
                        phone=product.supplier.phone,
                        role=product.supplier.role
                    )
                except Exception as e:
                    print(f"Error converting supplier: {e}")
                    supplier = None

            # Convert variants using model's to_dict method
            variants = []
            for variant in (product.variants or []):
                try:
                    variant_dict = variant.to_dict(include_images=True)
                    variants.append(
                        ProductVariantResponse.model_validate(variant_dict))
                except Exception as e:
                    print(f"Error converting variant {variant.id}: {e}")
                    continue

            # Get primary variant
            primary_variant = variants[0] if variants else None

            return ProductResponse(
                id=product.id,
                name=product.name,
                description=product.description,
                category_id=product.category_id,
                supplier_id=product.supplier_id,
                featured=product.featured,
                rating=product.rating,
                review_count=product.review_count,
                origin=product.origin,
                is_active=product.is_active,
                price_range=PriceRange(
                    min=product.price_range["min"], max=product.price_range["max"]),
                in_stock=product.in_stock,
                availability_status=product.availability_status,
                created_at=product.created_at.isoformat() if product.created_at else "",
                updated_at=product.updated_at.isoformat() if product.updated_at else None,
                category=category,
                supplier=supplier,
                variants=variants,
                primary_variant=primary_variant
            )
        except Exception as e:
            print(f"Error converting product {product.id}: {e}")
            # Return minimal product data
            return ProductResponse(
                id=product.id,
                name=getattr(product, 'name', ''),
                description=getattr(product, 'description', ''),
                category_id=product.category_id,
                supplier_id=product.supplier_id,
                featured=getattr(product, 'featured', False),
                rating=getattr(product, 'rating', 0.0),
                review_count=getattr(product, 'review_count', 0),
                origin=getattr(product, 'origin', ''),
                is_active=getattr(product, 'is_active', True),
                availability_status="out_of_stock",
                price_range=PriceRange(min=0, max=0),
                in_stock=False,
                created_at=product.created_at.isoformat() if product.created_at else "",
                updated_at=product.updated_at.isoformat() if product.updated_at else None,
                category=None,
                supplier=None,
                variants=[],
                primary_variant=None
            )

    async def get_products(
        self,
        page: int = 1,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> Dict[str, Any]:
        """Get products with filtering and pagination."""
        print(
            f"Getting products: page={page}, limit={limit}, filters={filters}")
        offset = (page - 1) * limit

        # Build filter conditions
        base_conditions = [Product.is_active == True]
        
        if filters:
            if filters.get("q"):
                search_term = f"%{filters['q']}%"
                base_conditions.append(
                    or_(
                        Product.name.ilike(search_term),
                        Product.description.ilike(search_term)
                    )
                )
            
            if filters.get("min_rating") is not None:
                base_conditions.append(Product.rating >= filters["min_rating"])
            
            if filters.get("max_rating") is not None:
                base_conditions.append(Product.rating <= filters["max_rating"])

            if filters.get("featured"):
                base_conditions.append(or_(Product.is_featured.is_(True), Product.featured.is_(True)))
        
        # Build subquery for filtering by category
        if filters and filters.get("category"):
            # Get category first
            cat_query = select(Category.id).where(Category.name == filters['category'])
            cat_result = await self.db.execute(cat_query)
            category_id = cat_result.scalar_one_or_none()
            if category_id:
                base_conditions.append(Product.category_id == category_id)
        
        # Build subquery for filtering by variant properties
        if filters:
            price_filters = []
            if filters.get("min_price") is not None:
                price_filters.append(ProductVariant.base_price >= filters["min_price"])
            
            if filters.get("max_price") is not None:
                price_filters.append(ProductVariant.base_price <= filters["max_price"])
            
            if filters.get("availability") is not None:
                if filters["availability"]:
                    # Join with inventory and check quantity_available > 0
                    price_filters.append(
                        ProductVariant.inventory.has(
                            Inventory.quantity_available > 0
                        )
                    )
                else:
                    # Join with inventory and check quantity_available == 0 or no inventory
                    price_filters.append(
                        or_(
                            ~ProductVariant.inventory.has(),
                            ProductVariant.inventory.has(
                                Inventory.quantity_available == 0
                            )
                        )
                    )
            
            if filters.get("sale"):
                price_filters.append(
                    and_(
                        ProductVariant.sale_price.isnot(None),
                        ProductVariant.sale_price < ProductVariant.base_price
                    )
                )
            
            if price_filters:
                # Use EXISTS with correlated subquery for better performance
                variant_subquery = (
                    select(1)
                    .where(
                        and_(
                            ProductVariant.product_id == Product.id,
                            *price_filters
                        )
                    )
                    .exists()
                )
                base_conditions.append(variant_subquery)
        
        # Build the main query
        query = (
            select(Product)
            .where(and_(*base_conditions))
            .options(
                selectinload(Product.category),
                selectinload(Product.supplier),
                selectinload(Product.variants).selectinload(ProductVariant.images),
                selectinload(Product.variants).selectinload(ProductVariant.inventory)
            )
        )

        # Apply sorting
        if hasattr(Product, sort_by):
            if sort_order.lower() == "desc":
                query = query.order_by(getattr(Product, sort_by).desc())
            else:
                query = query.order_by(getattr(Product, sort_by).asc())

        # Get total count for pagination - must match the main query filters
        count_query = select(func.count(Product.id))
        for condition in base_conditions:
            count_query = count_query.where(condition)

        count_result = await self.db.execute(count_query)
        total = count_result.scalar()

        # Apply pagination
        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        products = result.scalars().all()

        print(f"Found {len(products)} products in database")
        print(f"Total count from count query: {total}")

        # Convert to response format
        products_data = []
        for product in products:
            try:
                product_response = self._convert_product_to_response(product)
                products_data.append(product_response)
            except Exception as e:
                print(f"Error converting product {product.id}: {e}")
                continue

        print(f"Successfully converted {len(products_data)} products")

        return {
            "data": products_data,
            "total": total,
            "page": page,
            "per_page": limit,
            "total_pages": (total + limit - 1) // limit
        }

    async def get_featured_products(self, limit: int = 4) -> List[ProductResponse]:
        """Fetch featured products with related data."""
        print(f"Fetching {limit} featured products...")

        # ✅ Use outerjoin if variants might be missing
        query = (
            select(Product)
            .options(
                selectinload(Product.category),
                selectinload(Product.supplier),
                selectinload(Product.variants).selectinload(
                    ProductVariant.images),
                selectinload(Product.variants).selectinload(ProductVariant.inventory)
            )
            .where(or_(Product.is_featured.is_(True), Product.featured.is_(True)))  # support new and legacy flags
            .order_by(Product.created_at.desc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        products = result.scalars().unique().all()  # ✅ ensure uniqueness with .unique()

        print(f"Found {len(products)} featured products in DB.")
        for p in products:
            print(
                f"  - {p.name} (Featured: {p.is_featured or p.featured}, Variants: {len(p.variants)})")

        if not products:
            print(
                "⚠️ No featured products found. Check your DB data or 'featured' column values.")

        return [self._convert_product_to_response(product) for product in products]

    async def get_popular_products(self, limit: int = 4) -> List[ProductResponse]:
        """Get popular products based on cart additions or fallback to highest rated products."""
        # First, try to get products based on cart additions
        query = (
            select(Product, func.count(CartItem.id).label("added_to_cart"))
            .join(Product.variants)
            .join(CartItem, CartItem.variant_id == ProductVariant.id)
            .group_by(Product.id)
            .order_by(func.count(CartItem.id).desc())
            .limit(limit)
            .options(
                selectinload(Product.category),
                selectinload(Product.supplier),
                selectinload(Product.variants).selectinload(
                    ProductVariant.images),
                selectinload(Product.variants).selectinload(ProductVariant.inventory)
            )
        )

        result = await self.db.execute(query)
        rows = result.all()

        # If no products found (no cart items), fallback to highest rated products
        if not rows:
            fallback_query = select(Product).options(
                selectinload(Product.category),
                selectinload(Product.supplier),
                selectinload(Product.variants).selectinload(
                    ProductVariant.images),
                selectinload(Product.variants).selectinload(ProductVariant.inventory)
            ).order_by(Product.rating.desc(), Product.review_count.desc()).limit(limit)

            fallback_result = await self.db.execute(fallback_query)
            fallback_products = fallback_result.scalars().all()

            return [self._convert_product_to_response(product) for product in fallback_products]

        # Process cart-based popular products
        products = [row[0] for row in rows]  # Extract Product objects
        return [self._convert_product_to_response(product) for product in products]

    async def get_recommended_products(self, product_id: UUID, limit: int = 4) -> List[ProductResponse]:
        """
        Get smart product recommendations using multiple algorithms:
        - Complementary (cross-sell): Products frequently bought together
        - Similar (alternative): Same category, similar price range
        - Behavioral (social proof): Popular based on orders and reviews
        """
        from services.products.recommendations import RecommendationService
        
        recommendation_service = RecommendationService(self.db)
        return await recommendation_service.get_smart_recommendations(product_id, limit)

    async def get_categories(self) -> List[CategoryResponse]:
        """Get all categories with their product counts."""
        query = (
            select(
                Category,
                func.count(Product.id).label("product_count")
            )
            .outerjoin(Product, Product.category_id == Category.id)
            .where(Category.is_active == True)
            .group_by(Category.id)
        )
        result = await self.db.execute(query)
        categories_with_counts = result.all()

        categories = []
        for category, product_count in categories_with_counts:
            categories.append(CategoryResponse(
                id=category.id,
                name=category.name,
                description=category.description,
                image_url=category.image_url,
                is_active=category.is_active,
                product_count=product_count,
                created_at=category.created_at.isoformat() if category.created_at else "",
                updated_at=category.updated_at.isoformat() if category.updated_at else None
            ))

        return categories

    async def get_category_by_id(self, category_id: UUID) -> Optional[CategoryResponse]:
        """Get Category by ID."""
        query = select(Category).where(Category.id == category_id)
        result = await self.db.execute(query)
        category = result.scalar_one_or_none()

        if category:
            # Get product count for this category
            product_count_query = select(func.count(Product.id)).where(
                Product.category_id == category.id,
                Product.is_active == True
            )
            product_count_result = await self.db.execute(product_count_query)
            product_count = product_count_result.scalar()
            
            return CategoryResponse(
                id=category.id,
                name=category.name,
                description=category.description,
                image_url=category.image_url,
                is_active=category.is_active,
                product_count=product_count,
                created_at=category.created_at.isoformat() if category.created_at else "",
                updated_at=category.updated_at.isoformat() if category.updated_at else None
            )
        return None

    async def get_product_by_id(self, product_id: UUID) -> Optional[ProductResponse]:
        """Get product by ID."""
        query = select(Product).options(
            selectinload(Product.category),
            selectinload(Product.supplier),
            selectinload(Product.variants).selectinload(ProductVariant.images),
            selectinload(Product.variants).selectinload(ProductVariant.inventory)
        ).where(Product.id == product_id)

        result = await self.db.execute(query)
        product = result.scalar_one_or_none()

        if product:
            return self._convert_product_to_response(product)
        return None

    async def get_variant_by_id(self, variant_id: UUID) -> Optional[ProductVariantResponse]:
        """Get product variant by ID."""
        query = select(ProductVariant).options(
            selectinload(ProductVariant.images),
            selectinload(ProductVariant.inventory)
        ).where(ProductVariant.id == variant_id)

        result = await self.db.execute(query)
        variant = result.scalar_one_or_none()

        if variant:
            return self._convert_variant_to_response(variant)
        return None

    async def get_product_variants(self, product_id: UUID) -> List[ProductVariantResponse]:
        """Get all variants for a product."""
        query = select(ProductVariant).options(
            selectinload(ProductVariant.images),
            selectinload(ProductVariant.inventory)
        ).where(ProductVariant.product_id == product_id)

        result = await self.db.execute(query)
        variants = result.scalars().all()

        return [self._convert_variant_to_response(variant) for variant in variants]

    async def generate_qr_code(self, variant_id: UUID) -> Optional[str]:
        """Generate QR code for a product variant."""
        from services.barcode import BarcodeService
        barcode_service = BarcodeService(self.db)
        
        try:
            codes = await barcode_service.generate_variant_codes(variant_id)
            return codes.get("qr_code")
        except Exception as e:
            print(f"Error generating QR code: {e}")
            return None

    async def generate_barcode(self, variant_id: UUID) -> Optional[str]:
        """Generate barcode for a product variant."""
        from services.barcode import BarcodeService
        barcode_service = BarcodeService(self.db)
        
        try:
            codes = await barcode_service.generate_variant_codes(variant_id)
            return codes.get("barcode")
        except Exception as e:
            print(f"Error generating barcode: {e}")
            return None
    
    async def generate_variant_codes(self, variant_id: UUID) -> dict:
        """Generate both barcode and QR code for a product variant."""
        from services.barcode import BarcodeService
        barcode_service = BarcodeService(self.db)
        
        try:
            return await barcode_service.generate_variant_codes(variant_id)
        except Exception as e:
            print(f"Error generating variant codes: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to generate codes: {str(e)}")
    
    async def update_variant_codes(self, variant_id: UUID, barcode: Optional[str] = None, qr_code: Optional[str] = None) -> dict:
        """Update barcode and/or QR code for a product variant."""
        from services.barcode import BarcodeService
        barcode_service = BarcodeService(self.db)
        
        try:
            return await barcode_service.update_variant_codes(variant_id, barcode, qr_code)
        except Exception as e:
            print(f"Error updating variant codes: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to update codes: {str(e)}")

    async def search_products(
        self, 
        query: str, 
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Advanced search for products with fuzzy matching and weighted ranking using pg_trgm.
        """
        if not query or len(query.strip()) < 2:
            return []
            
        query = query.strip().lower()
        
        # Build base conditions
        base_conditions = ["p.is_active = true"]
        params = {
            "query": query,
            "similarity_threshold": float(self.similarity_threshold),
            "limit": limit,
            "exact_weight": float(self.weights["exact"]),
            "prefix_weight": float(self.weights["prefix"]),
            "fuzzy_weight": float(self.weights["fuzzy"]),
            "name_weight": float(self.product_field_weights["name"]),
            "desc_weight": float(self.product_field_weights["description"]),
            "cat_weight": float(self.product_field_weights["category"]),
            "tag_weight": float(self.product_field_weights["tags"])
        }
        
        # Add filters
        if filters:
            if filters.get("category_id"):
                base_conditions.append("p.category_id = :category_id")
                params["category_id"] = filters["category_id"]
                
            if filters.get("min_price") is not None:
                base_conditions.append("""
                    EXISTS (
                        SELECT 1 FROM product_variants pv 
                        WHERE pv.product_id = p.id 
                        AND pv.base_price >= :min_price
                    )
                """)
                params["min_price"] = filters["min_price"]
                
            if filters.get("max_price") is not None:
                base_conditions.append("""
                    EXISTS (
                        SELECT 1 FROM product_variants pv 
                        WHERE pv.product_id = p.id 
                        AND pv.base_price <= :max_price
                    )
                """)
                params["max_price"] = filters["max_price"]
        
        where_clause = " AND ".join(base_conditions)
        
        sql_query = text(f"""
            SELECT 
                p.id,
                p.name,
                p.description,
                p.rating,
                p.review_count,
                c.name as category_name,
                -- Calculate weighted relevance score
                (
                    -- Name matching (highest weight)
                    CASE WHEN LOWER(p.name) = :query THEN CAST(:exact_weight AS FLOAT) * CAST(:name_weight AS FLOAT)
                         WHEN LOWER(p.name) LIKE CONCAT(:query, '%') THEN CAST(:prefix_weight AS FLOAT) * CAST(:name_weight AS FLOAT) * 0.9
                         WHEN LOWER(p.name) LIKE CONCAT('%', :query, '%') THEN CAST(:prefix_weight AS FLOAT) * CAST(:name_weight AS FLOAT) * 0.7
                         ELSE similarity(LOWER(p.name), :query) * CAST(:fuzzy_weight AS FLOAT) * CAST(:name_weight AS FLOAT)
                    END +
                    -- Description matching
                    CASE WHEN LOWER(p.description) LIKE CONCAT('%', :query, '%') THEN CAST(:prefix_weight AS FLOAT) * CAST(:desc_weight AS FLOAT)
                         ELSE similarity(LOWER(p.description), :query) * CAST(:fuzzy_weight AS FLOAT) * CAST(:desc_weight AS FLOAT)
                    END +
                    -- Category matching
                    CASE WHEN LOWER(c.name) = :query THEN CAST(:exact_weight AS FLOAT) * CAST(:cat_weight AS FLOAT)
                         WHEN LOWER(c.name) LIKE CONCAT(:query, '%') THEN CAST(:prefix_weight AS FLOAT) * CAST(:cat_weight AS FLOAT)
                         WHEN LOWER(c.name) LIKE CONCAT('%', :query, '%') THEN CAST(:prefix_weight AS FLOAT) * CAST(:cat_weight AS FLOAT) * 0.7
                         ELSE similarity(LOWER(c.name), :query) * CAST(:fuzzy_weight AS FLOAT) * CAST(:cat_weight AS FLOAT)
                    END +
                    -- Boost for higher rated products
                    (COALESCE(p.rating, 0) / 5.0) * 0.1 +
                    -- Boost for products with more reviews
                    LEAST(COALESCE(p.review_count, 0) / 100.0, 0.1)
                ) as relevance_score
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            WHERE {where_clause}
            AND (
                LOWER(p.name) LIKE CONCAT('%', :query, '%')
                OR LOWER(p.description) LIKE CONCAT('%', :query, '%')
                OR LOWER(c.name) LIKE CONCAT('%', :query, '%')
                OR similarity(LOWER(p.name), :query) > :similarity_threshold
                OR similarity(LOWER(p.description), :query) > :similarity_threshold
                OR similarity(LOWER(c.name), :query) > :similarity_threshold
            )
            ORDER BY relevance_score DESC, p.rating DESC, p.review_count DESC
            LIMIT :limit
        """)
        
        try:
            result = await self.db.execute(sql_query, params)
            
            products = []
            for row in result:
                products.append({
                    "id": str(row.id),
                    "name": row.name,
                    "description": row.description,
                    "rating": float(row.rating) if row.rating else 0.0,
                    "review_count": row.review_count or 0,
                    "category_name": row.category_name,
                    "relevance_score": float(row.relevance_score),
                    "type": "product"
                })
                
            return products
        except Exception as e:
            logger.error(f"Error in search_products: {e}")
            return []

    async def search_categories(
        self, 
        query: str, 
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search categories with simple text matching.
        """
        if not query or len(query.strip()) < 2:
            return []
            
        query = query.strip().lower()
        
        # Build simple query without similarity function
        base_query = select(
            Category.id,
            Category.name,
            Category.description,
            Category.image_url,
            func.count(Product.id).label('product_count')
        ).select_from(
            Category.__table__.outerjoin(Product.__table__, 
                and_(Category.id == Product.category_id, Product.is_active == True)
            )
        ).where(
            and_(
                Category.is_active == True,
                or_(
                    func.lower(Category.name).like(f'%{query}%'),
                    func.lower(Category.description).like(f'%{query}%')
                )
            )
        ).group_by(
            Category.id, Category.name, Category.description, Category.image_url
        ).order_by(
            func.count(Product.id).desc(),
            Category.name
        ).limit(limit)
        
        try:
            result = await self.db.execute(base_query)
            categories = result.fetchall()
            
            # Convert to dict format
            category_list = []
            for category in categories:
                category_dict = {
                    "id": str(category.id),
                    "name": category.name,
                    "description": category.description,
                    "image_url": category.image_url,
                    "product_count": category.product_count,
                    "type": "category"
                }
                category_list.append(category_dict)
            
            return category_list
            
        except Exception as e:
            logger.error(f"Error in search_categories: {e}")
            return []

    async def create_product(self, product_data: ProductCreate, supplier_id: UUID) -> ProductResponse:
        """Create a new product."""
        # Create product
        db_product = Product(
            id=uuid7(),
            name=product_data.name,
            slug=product_data.slug,
            description=product_data.description,
            short_description=product_data.short_description,
            category_id=product_data.category_id,
            supplier_id=supplier_id,
            origin=product_data.origin,
            is_featured=product_data.is_featured,
            is_bestseller=product_data.is_bestseller
        )

        self.db.add(db_product)
        await self.db.flush()  # Get the product ID

        # Create variants
        for v_idx, variant_data in enumerate(product_data.variants):
            # Auto-generate SKU: PROD-{product_id[:8]}-{variant_index}
            # Format: First 3 chars of product name + first 8 chars of product ID + variant index
            product_prefix = db_product.name[:3].upper().replace(' ', '')
            auto_sku = f"{product_prefix}-{str(db_product.id)[:8]}-{v_idx}"
            final_sku = variant_data.sku if variant_data.sku else auto_sku
            
            # Create variant first to get the ID
            db_variant = ProductVariant(
                id=uuid7(),
                product_id=db_product.id,
                sku=final_sku,
                name=variant_data.name,
                barcode=None,  # Will be set after generation
                qr_code=None,  # Will be set after generation
                base_price=variant_data.base_price,
                sale_price=variant_data.sale_price,
                attributes=variant_data.attributes or {},
                specifications=variant_data.specifications,
                dietary_tags=variant_data.dietary_tags or [],
                tags=variant_data.tags,
                availability_status=variant_data.availability_status or "available",
                view_count=0,
                purchase_count=0
            )
            self.db.add(db_variant)
            await self.db.flush()  # Get variant ID
            
            # Now generate barcode and QR code with the actual variant ID
            from services.barcode import BarcodeService
            barcode_service = BarcodeService(self.db)
            
            # Generate QR code data for this specific variant
            qr_data = f"https://banwee.com/products/variant/{db_variant.id}"
            
            try:
                barcode_b64 = barcode_service.generate_barcode(final_sku)
                qr_code_b64 = barcode_service.generate_qr_code(qr_data)
                
                # Update the variant with generated codes
                db_variant.barcode = barcode_b64
                db_variant.qr_code = qr_code_b64
                
            except Exception as e:
                print(f"Warning: Failed to generate codes for variant {final_sku}: {e}")
                # Leave as None if generation fails
            
            # ALWAYS create inventory record for the variant (even if stock is 0)
            from models.inventories import Inventory, WarehouseLocation
            
            # Get warehouse location from variant data if provided, otherwise use default
            warehouse_location_id = None
            if hasattr(variant_data, 'warehouse_location_id') and variant_data.warehouse_location_id:
                # Use the warehouse location provided in variant data
                warehouse_location_id = variant_data.warehouse_location_id
            else:
                # Try to find an existing warehouse location
                default_location_result = await self.db.execute(
                    select(WarehouseLocation).where(WarehouseLocation.name == "Main Warehouse")
                )
                default_location = default_location_result.scalar_one_or_none()
                
                if not default_location:
                    # Try "Default" as fallback
                    default_location_result = await self.db.execute(
                        select(WarehouseLocation).where(WarehouseLocation.name == "Default")
                    )
                    default_location = default_location_result.scalar_one_or_none()
                
                if default_location:
                    warehouse_location_id = default_location.id
            
            # Get stock quantity from variant_data, default to 0 if not provided
            stock_quantity = getattr(variant_data, 'stock', 0) if hasattr(variant_data, 'stock') else 0
            
            # Create inventory record - ALWAYS, even if stock is 0
            inventory = Inventory(
                id=uuid7(),
                variant_id=db_variant.id,
                location_id=warehouse_location_id,
                quantity_available=stock_quantity,
                quantity=stock_quantity, # Legacy field for backward compatibility
                low_stock_threshold=10,
                reorder_point=5,
                inventory_status="active"
            )
            self.db.add(inventory)
            
            # Create variant images from CDN URLs
            if variant_data.image_urls:
                from models.product import ProductImage
                for img_idx, image_url in enumerate(variant_data.image_urls):
                    db_image = ProductImage(
                        id=uuid7(),
                        variant_id=db_variant.id,
                        url=image_url,
                        is_primary=(img_idx == 0),  # First image is primary
                        sort_order=img_idx
                    )
                    self.db.add(db_image)

        await self.db.commit()

        # Return the created product
        return await self.get_product_by_id(db_product.id)

    async def update_product(
        self,
        product_id: UUID,
        product_data: ProductUpdate,
        user_id: UUID,
        is_admin: bool = False
    ) -> ProductResponse:
        """Update a product and its variants."""
        from models.inventories import Inventory
        
        logger.info(f"Updating product {product_id} with data: {product_data.dict(exclude_unset=True)}")
        
        query = select(Product).options(
            selectinload(Product.variants).selectinload(ProductVariant.images),
            selectinload(Product.variants).selectinload(ProductVariant.inventory)
        ).where(Product.id == product_id)
        result = await self.db.execute(query)
        product = result.scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        # Check if user owns the product (for suppliers) or is admin
        if not is_admin and product.supplier_id != user_id:
            raise HTTPException(
                status_code=403, detail="Not authorized to update this product")

        # Update product fields
        update_dict = product_data.dict(exclude_unset=True, exclude={'variants'})
        for field, value in update_dict.items():
            setattr(product, field, value)
        
        logger.info(f"Updated product fields: {update_dict}")

        # Handle variant updates if provided
        if product_data.variants is not None:
            logger.info(f"Processing {len(product_data.variants)} variants")
            logger.info(f"Variant data: {[v.dict(exclude_unset=True) for v in product_data.variants]}")
            existing_variant_ids = {str(v.id) for v in product.variants}
            updated_variant_ids = set()
            
            for idx, variant_data in enumerate(product_data.variants):
                logger.info(f"Processing variant {idx}: id={variant_data.id}, data={variant_data.dict(exclude_unset=True)}")
                
                if variant_data.id:
                    # Update existing variant
                    variant_id = variant_data.id
                    updated_variant_ids.add(str(variant_id))
                    
                    variant = next((v for v in product.variants if v.id == variant_id), None)
                    if variant:
                        logger.info(f"Updating existing variant {variant_id}")
                        # Update variant fields - only update fields that were explicitly provided
                        variant_dict = variant_data.dict(exclude_unset=True, exclude={'id', 'images', 'stock'})
                        logger.info(f"Fields to update: {list(variant_dict.keys())}")
                        
                        # Flag to track if we made any changes
                        made_changes = False
                        
                        for field, value in variant_dict.items():
                            if value is not None:  # Only update if value is provided
                                old_value = getattr(variant, field, None)
                                if old_value != value:  # Only if value actually changed
                                    setattr(variant, field, value)
                                    made_changes = True
                                    logger.info(f"Updated variant.{field}: {old_value} -> {value}")
                        
                        # Handle stock update via inventory
                        if variant_data.stock is not None:
                            if not variant.inventory:
                                # Create inventory if it doesn't exist
                                logger.info(f"Creating new inventory for variant {variant_id} with stock {variant_data.stock}")
                                inventory = Inventory(
                                    id=uuid7(),
                                    variant_id=variant.id,
                                    quantity=variant_data.stock,
                                    quantity_available=variant_data.stock,
                                    low_stock_threshold=10
                                )
                                self.db.add(inventory)
                            else:
                                # Update existing inventory
                                logger.info(f"Updating inventory for variant {variant_id}: {variant.inventory.quantity} -> {variant_data.stock}")
                                variant.inventory.quantity = variant_data.stock
                                variant.inventory.quantity_available = variant_data.stock
                        
                        # Handle images if provided (only if explicitly set in the request)
                        # ID-based image management: update existing, create new, delete removed
                        logger.info(f"🔍 Checking images for variant {variant_id}")
                        logger.info(f"🔍 hasattr fields_set: {hasattr(variant_data, 'fields_set')}")
                        if hasattr(variant_data, 'fields_set'):
                            logger.info(f"🔍 fields_set: {variant_data.fields_set}")
                            logger.info(f"🔍 'images' in fields_set: {'images' in variant_data.fields_set}")
                        logger.info(f"🔍 variant_data.images: {variant_data.images}")
                        
                        # Process images if they're provided (not None)
                        if variant_data.images is not None:
                            logger.info(f"Updating images for variant {variant_id}: {len(variant_data.images) if variant_data.images else 0} images")
                            
                            if variant_data.images:
                                # Collect incoming image IDs (both UUID objects and strings)
                                incoming_image_ids = set()
                                for img_data in variant_data.images:
                                    if isinstance(img_data, dict) and img_data.get('id'):
                                        img_id = img_data.get('id')
                                        # Convert to UUID if it's a string
                                        if isinstance(img_id, str):
                                            try:
                                                img_id = uuid.UUID(img_id)
                                            except ValueError:
                                                continue
                                        incoming_image_ids.add(img_id)
                                
                                # Delete images that are no longer in the list
                                for img in variant.images[:]:
                                    if img.id not in incoming_image_ids:
                                        logger.info(f"Deleting removed image {img.id}")
                                        self.db.delete(img)
                                
                                # Update existing images or create new ones
                                for img_idx, img_data in enumerate(variant_data.images):
                                    if isinstance(img_data, dict):
                                        img_id = img_data.get('id')
                                        
                                        if img_id:
                                            # Convert string ID to UUID if needed
                                            if isinstance(img_id, str):
                                                try:
                                                    img_id = uuid.UUID(img_id)
                                                except ValueError:
                                                    logger.warning(f"Invalid image ID format: {img_id}")
                                                    continue
                                            
                                            # Update existing image
                                            existing_img = next((img for img in variant.images if img.id == img_id), None)
                                            if existing_img:
                                                logger.info(f"Updating existing image {img_id}")
                                                existing_img.url = img_data.get('url', existing_img.url)
                                                existing_img.alt_text = img_data.get('alt_text', existing_img.alt_text)
                                                existing_img.is_primary = img_data.get('is_primary', existing_img.is_primary)
                                                existing_img.sort_order = img_data.get('sort_order', existing_img.sort_order)
                                            else:
                                                logger.warning(f"Image ID {img_id} not found in variant images, skipping")
                                        else:
                                            # Create new image (no ID provided)
                                            logger.info(f"Creating new image at index {img_idx}")
                                            image = ProductImage(
                                                id=uuid7(),
                                                variant_id=variant.id,
                                                url=img_data.get('url', ''),
                                                alt_text=img_data.get('alt_text', ''),
                                                is_primary=img_data.get('is_primary', False),
                                                sort_order=img_data.get('sort_order', img_idx)
                                            )
                                            self.db.add(image)
                            else:
                                # Empty images array means delete all images
                                logger.info(f"Deleting all images for variant {variant_id}")
                                for img in variant.images[:]:
                                    self.db.delete(img)
                    else:
                        logger.warning(f"Variant {variant_id} not found in product variants")
                else:
                    # Create new variant
                    logger.info(f"Creating new variant")
                    new_variant_dict = variant_data.dict(exclude_unset=True, exclude={'id', 'images', 'stock'})
                    new_variant = ProductVariant(
                        product_id=product_id,
                        **new_variant_dict
                    )
                    
                    # Generate SKU if not provided
                    if not new_variant.sku:
                        new_variant.sku = await self._generate_sku(product)
                    
                    self.db.add(new_variant)
                    await self.db.flush()  # Get the new variant ID
                    updated_variant_ids.add(str(new_variant.id))
                    
                    logger.info(f"Created new variant with ID {new_variant.id}")
                    
                    # Create inventory for new variant
                    if variant_data.stock is not None:
                        inventory = Inventory(
                            id=uuid7(),
                            variant_id=new_variant.id,
                            quantity=variant_data.stock,
                            quantity_available=variant_data.stock,
                            low_stock_threshold=10
                        )
                        self.db.add(inventory)
                    
                    # Add images for new variant
                    if variant_data.images:
                        for img_data in variant_data.images:
                            if isinstance(img_data, dict):
                                image = ProductImage(
                                    id=uuid7(),
                                    variant_id=new_variant.id,
                                    url=img_data.get('url', ''),
                                    alt_text=img_data.get('alt_text', ''),
                                    is_primary=img_data.get('is_primary', False),
                                    sort_order=img_data.get('sort_order', 0)
                                )
                                self.db.add(image)
            
            # Delete variants that were removed (keep at least one variant)
            variants_to_delete = existing_variant_ids - updated_variant_ids
            if variants_to_delete and len(updated_variant_ids) > 0:
                logger.info(f"Deleting {len(variants_to_delete)} variants: {variants_to_delete}")
                for variant in product.variants[:]:
                    if str(variant.id) in variants_to_delete:
                        # Delete associated inventory
                        if variant.inventory:
                            self.db.delete(variant.inventory)
                        # Delete associated images
                        for img in variant.images:
                            self.db.delete(img)
                        self.db.delete(variant)

        await self.db.commit()
        logger.info(f"Product {product_id} updated successfully")

        # Return the updated product
        return await self.get_product_by_id(product_id)

    async def delete_product(self, product_id: UUID, user_id: UUID, is_admin: bool = False):
        """Delete a product and all its associated data (variants, inventory, reviews, cart items, wishlist items)."""
        from models.orders import OrderItem
        
        query = select(Product).where(Product.id == product_id)
        result = await self.db.execute(query)
        product = result.scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        # Check if user owns the product (for suppliers) or is admin
        if not is_admin and product.supplier_id != user_id:
            raise HTTPException(
                status_code=403, detail="Not authorized to delete this product")
        
        # Check if product has any order items (prevent deletion of ordered products)
        variant_ids = [variant.id for variant in product.variants]
        if variant_ids:
            order_items = (await self.db.execute(
                select(OrderItem).where(OrderItem.variant_id.in_(variant_ids))
            )).scalars().first()
            
            if order_items:
                raise HTTPException(
                    status_code=400, 
                    detail="Cannot delete product that has been ordered. Product has order history."
                )

        # Delete all reviews for this product
        reviews = (await self.db.execute(
            select(Review).where(Review.product_id == product_id)
        )).scalars().all()
        for review in reviews:
            await self.db.delete(review)

        # Delete all cart items for this product
        cart_items = (await self.db.execute(
            select(CartItem).where(CartItem.product_id == product_id)
        )).scalars().all()
        for cart_item in cart_items:
            await self.db.delete(cart_item)

        # Delete all wishlist items for this product
        wishlist_items = (await self.db.execute(
            select(WishlistItem).where(WishlistItem.product_id == product_id)
        )).scalars().all()
        for wishlist_item in wishlist_items:
            await self.db.delete(wishlist_item)

        # Delete the product (this will cascade delete variants and inventory due to cascade="all, delete-orphan")
        await self.db.delete(product)
        await self.db.commit()
