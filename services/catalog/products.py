from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text, desc
from sqlalchemy.orm import selectinload
from typing import Optional, List, Dict, Any, TypeVar
from uuid import UUID
from core.utils.uuid_utils import uuid7
from models.catalog.product import Product, ProductVariant, ProductImage, ProductStatus, AvailabilityStatus
from models.catalog.inventories import Inventory
from models.commerce.cart import CartItem
from schemas.catalog.product import (
    ProductCreate, ProductUpdate, ProductResponse,
    ProductVariantResponse, ProductImageResponse, PriceRange, ProductListResponse
)
from schemas.catalog.inventory import InventoryResponse
from core.exceptions import APIException
from core.logging import get_structured_logger
from fastapi import HTTPException
from datetime import datetime, timezone, date

logger = get_structured_logger(__name__)


class ProductService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _convert_image_to_response(self, image: ProductImage) -> ProductImageResponse:
        """Convert ProductImage model to response format."""
        created_at_val = image.created_at
        if isinstance(created_at_val, (datetime, date)):
            created_at_str = created_at_val.isoformat()
        else:
            created_at_str = created_at_val or ""

        return ProductImageResponse(
            id=image.id,
            variant_id=image.variant_id,
            url=image.url,
            alt_text=image.alt_text,
            is_primary=image.is_primary,
            sort_order=image.sort_order,
            format=image.format,
            created_at=created_at_str
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
                created_at=variant.created_at.isoformat() if isinstance(variant.created_at, (datetime, date)) else (variant.created_at or ""),
                updated_at=variant.updated_at.isoformat() if isinstance(variant.updated_at, (datetime, date)) else variant.updated_at
            )

    def _convert_product_to_response(self, product: Product) -> ProductResponse:
        """Convert Product model to response format."""
        try:
            # Convert variants using model's to_dict method with proper validation
            variants = []
            for variant in (product.variants or []):
                try:
                    variant_dict = variant.to_dict(include_images=True)
                    
                    # Fix datetime fields (only call isoformat on datetime objects)
                    if 'created_at' in variant_dict and variant_dict['created_at']:
                        if isinstance(variant_dict['created_at'], (datetime, date)):
                            variant_dict['created_at'] = variant_dict['created_at'].isoformat()
                    if 'updated_at' in variant_dict and variant_dict['updated_at']:
                        if isinstance(variant_dict['updated_at'], (datetime, date)):
                            variant_dict['updated_at'] = variant_dict['updated_at'].isoformat()
                    
                    # Fix dietary_tags - convert string to list
                    if 'dietary_tags' in variant_dict and isinstance(variant_dict['dietary_tags'], str):
                        variant_dict['dietary_tags'] = [tag.strip() for tag in variant_dict['dietary_tags'].split(',') if tag.strip()]
                    
                    # Fix tags - convert string to list  
                    if 'tags' in variant_dict and isinstance(variant_dict['tags'], str):
                        variant_dict['tags'] = [tag.strip() for tag in variant_dict['tags'].split(',') if tag.strip()]
                    
                    # Fix images datetime fields
                    if 'images' in variant_dict:
                        for img in variant_dict['images']:
                            if 'created_at' in img and img['created_at']:
                                if isinstance(img['created_at'], (datetime, date)):
                                    img['created_at'] = img['created_at'].isoformat()
                            if 'updated_at' in img and img['updated_at']:
                                if isinstance(img['updated_at'], (datetime, date)):
                                    img['updated_at'] = img['updated_at'].isoformat()
                    
                    # Add stock from inventory
                    if hasattr(variant, 'inventory') and variant.inventory:
                        variant_dict['stock'] = variant.inventory.quantity_available
                    else:
                        variant_dict['stock'] = 0
                    
                    variants.append(ProductVariantResponse.model_validate(variant_dict))
                except Exception as e:
                    logger.error(f"Error converting variant {variant.id}: {e}")
                    continue
            
            # Get primary variant
            primary_variant = None
            if product.variants:
                primary_variant = min(product.variants, key=lambda v: v.current_price)
                try:
                    primary_variant_dict = primary_variant.to_dict(include_images=True)
                    
                    # Fix datetime fields (only call isoformat on datetime objects)
                    if 'created_at' in primary_variant_dict and primary_variant_dict['created_at']:
                        if isinstance(primary_variant_dict['created_at'], (datetime, date)):
                            primary_variant_dict['created_at'] = primary_variant_dict['created_at'].isoformat()
                    if 'updated_at' in primary_variant_dict and primary_variant_dict['updated_at']:
                        if isinstance(primary_variant_dict['updated_at'], (datetime, date)):
                            primary_variant_dict['updated_at'] = primary_variant_dict['updated_at'].isoformat()
                    
                    # Fix dietary_tags and tags
                    if 'dietary_tags' in primary_variant_dict and isinstance(primary_variant_dict['dietary_tags'], str):
                        primary_variant_dict['dietary_tags'] = [tag.strip() for tag in primary_variant_dict['dietary_tags'].split(',') if tag.strip()]
                    if 'tags' in primary_variant_dict and isinstance(primary_variant_dict['tags'], str):
                        primary_variant_dict['tags'] = [tag.strip() for tag in primary_variant_dict['tags'].split(',') if tag.strip()]
                    
                    # Fix images datetime fields
                    if 'images' in primary_variant_dict:
                        for img in primary_variant_dict['images']:
                            if 'created_at' in img and img['created_at']:
                                if isinstance(img['created_at'], (datetime, date)):
                                    img['created_at'] = img['created_at'].isoformat()
                            if 'updated_at' in img and img['updated_at']:
                                if isinstance(img['updated_at'], (datetime, date)):
                                    img['updated_at'] = img['updated_at'].isoformat()
                    
                    # Add stock from inventory
                    if hasattr(primary_variant, 'inventory') and primary_variant.inventory:
                        primary_variant_dict['stock'] = primary_variant.inventory.quantity_available
                    else:
                        primary_variant_dict['stock'] = 0
                    
                    primary_variant = ProductVariantResponse.model_validate(primary_variant_dict)
                except Exception as e:
                    logger.error(f"Error converting primary variant: {e}")
                    primary_variant = None
            
            return ProductResponse(
                id=product.id,
                name=product.name,
                description=product.description,
                featured=product.is_featured,
                rating=product.rating_average,
                review_count=product.review_count,
                origin=getattr(product, 'origin', ''),
                is_active=product.is_active,
                availability_status=product.availability_status,
                price_range=product.price_range,
                in_stock=product.in_stock,
                created_at=product.created_at.isoformat() if isinstance(product.created_at, (datetime, date)) else (product.created_at or ""),
                updated_at=product.updated_at.isoformat() if isinstance(product.updated_at, (datetime, date)) else product.updated_at,
                category=product.category,
                variants=variants,
                primary_variant=primary_variant
            )
        except Exception as e:
            logger.error(f"Error converting product {product.id}: {e}")
            # Return minimal product data
            return ProductResponse(
                id=product.id,
                name=getattr(product, 'name', ''),
                description=getattr(product, 'description', ''),
                featured=getattr(product, 'is_featured', False),
                rating=getattr(product, 'rating_average', 0.0),
                review_count=getattr(product, 'review_count', 0),
                origin=getattr(product, 'origin', ''),
                is_active=getattr(product, 'is_active', True),
                availability_status="out_of_stock",
                price_range=PriceRange(min=0, max=0),
                in_stock=False,
                created_at=product.created_at.isoformat() if isinstance(product.created_at, (datetime, date)) else (product.created_at or ""),
                updated_at=product.updated_at.isoformat() if isinstance(product.updated_at, (datetime, date)) else product.updated_at,
                category=getattr(product, 'category', ''),
                variants=[],
                primary_variant=None
            )

    async def list(
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
                base_conditions.append(Product.rating_average >= filters["min_rating"])
            
            if filters.get("max_rating") is not None:
                base_conditions.append(Product.rating_average <= filters["max_rating"])

            if filters.get("featured"):
                base_conditions.append(Product.is_featured.is_(True))
        
        # Build subquery for filtering by category (now it's a string)
        if filters and filters.get("category"):
            base_conditions.append(Product.category == filters['category'])
        
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
        
        # Build the main query with simpler eager loading
        query = (
            select(Product)
            .where(and_(*base_conditions))
            .options(
                selectinload(Product.variants)
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

        # Convert to response format
        products_data = []
        for product in products:
            try:
                product_response = self._convert_product_to_response(product)
                products_data.append(product_response)
            except Exception as e:
                logger.error(f"Error converting product {product.id}: {e}")
                continue

        return {
            "data": products_data,
            "total": total,
            "page": page,
            "per_page": limit,
            "total_pages": (total + limit - 1) // limit
        }

    async def featured(self, limit: int = 4) -> List[ProductResponse]:
        """Fetch featured products with related data."""
        print(f"Fetching {limit} featured products...")

        # ✅ Use outerjoin if variants might be missing
        query = (
            select(Product)
            .options(
                selectinload(Product.variants).selectinload(
                    ProductVariant.images),
                selectinload(Product.variants).selectinload(ProductVariant.inventory)
            )
            .where(Product.is_featured.is_(True))
            .order_by(Product.created_at.desc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        products = result.scalars().unique().all()  # ✅ ensure uniqueness with .unique()

        print(f"Found {len(products)} featured products in DB.")
        for p in products:
            print(
                f"  - {p.name} (Featured: {p.is_featured}, Variants: {len(p.variants)})")

        if not products:
            print(
                "⚠️ No featured products found. Check your DB data or 'featured' column values.")

        return [self._convert_product_to_response(product) for product in products]

    async def popular(self, limit: int = 4) -> List[ProductResponse]:
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
                selectinload(Product.variants).selectinload(
                    ProductVariant.images),
                selectinload(Product.variants).selectinload(ProductVariant.inventory)
            ).order_by(Product.rating_average.desc(), Product.review_count.desc()).limit(limit)

            fallback_result = await self.db.execute(fallback_query)
            fallback_products = fallback_result.scalars().all()

            return [self._convert_product_to_response(product) for product in fallback_products]

        # Process cart-based popular products
        products = [row[0] for row in rows]  # Extract Product objects
        return [self._convert_product_to_response(product) for product in products]

    async def recommended(self, product_id: UUID, limit: int = 4) -> List[ProductResponse]:
        """
        Get smart product recommendations using multiple algorithms:
        - Complementary (cross-sell): Products frequently bought together
        - Similar (alternative): Same category, similar price range
        - Behavioral (social proof): Popular based on orders and reviews
        """
        from services.catalog.recommendations import RecommendationService
        
        recommendation_service = RecommendationService(self.db)
        return await recommendation_service.get_smart_recommendations(product_id, limit)

    async def by_category(self, slug: str) -> Optional[ProductResponse]:
        """Get category by slug and return products in that category."""
        # Find products in this category
        query = (
            select(Product)
            .options(
                selectinload(Product.variants).selectinload(
                    ProductVariant.images),
                selectinload(Product.variants).selectinload(
                    ProductVariant.inventory)
            )
            .where(Product.category == slug)
            .where(Product.product_status == ProductStatus.ACTIVE)
        )
        result = await self.db.execute(query)
        products = result.scalars().all()
        
        print(f"Found {len(products)} products")
        for product in products:
            print(f"Product: {product.name}, variants count: {len(product.variants) if product.variants else 0}")
        
        # Convert to responses
        product_responses = []
        for product in products:
            product_responses.append(self._convert_product_to_response(product))
        
        return ProductListResponse(
            products=product_responses,
            total=len(product_responses),
            page=1,
            per_page=len(product_responses),
            pages=1
        )

    async def get(self, product_id: UUID) -> Optional[ProductResponse]:
        """Get product by ID."""
        query = select(Product).options(
            selectinload(Product.variants).selectinload(ProductVariant.images),
            selectinload(Product.variants).selectinload(ProductVariant.inventory)
        ).where(Product.id == product_id)

        result = await self.db.execute(query)
        product = result.scalar_one_or_none()

        if product:
            return self._convert_product_to_response(product)
        return None

    async def get_variant(self, variant_id: UUID) -> Optional[ProductVariantResponse]:
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

    async def variants(self, product_id: UUID) -> List[ProductVariantResponse]:
        """Get all variants for a product."""
        query = select(ProductVariant).options(
            selectinload(ProductVariant.images),
            selectinload(ProductVariant.inventory)
        ).where(ProductVariant.product_id == product_id)

        result = await self.db.execute(query)
        variants = result.scalars().all()

        return [self._convert_variant_to_response(variant) for variant in variants]

    async def all_variants(
        self,
        page: int = 1,
        limit: int = 10,
        search: Optional[str] = None,
        product_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Get all product variants with filtering and pagination (for admin use)"""
        offset = (page - 1) * limit
        
        query = select(ProductVariant).options(
            selectinload(ProductVariant.product),
            selectinload(ProductVariant.inventory)
        )
        count_query = select(func.count(ProductVariant.id))
        
        conditions = []
        
        if search:
            conditions.append(
                or_(
                    ProductVariant.name.ilike(f"%{search}%"),
                    ProductVariant.sku.ilike(f"%{search}%")
                )
            )
        
        if product_id:
            conditions.append(ProductVariant.product_id == product_id)
        
        if conditions:
            query = query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))
        
        query = query.order_by(desc(ProductVariant.created_at)).offset(offset).limit(limit)
        
        result = await self.db.execute(query)
        variants = result.scalars().all()
        
        total = await self.db.scalar(count_query) or 0
        
        return {
            "data": [self._convert_variant_to_response(variant) for variant in variants],
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit if total > 0 else 0
        }

    async def create(self, product_data: ProductCreate, created_by: UUID) -> ProductResponse:
        """Create a new product."""
        # Create product
        db_product = Product(
            id=uuid7(),
            name=product_data.name,
            slug=product_data.slug,
            description=product_data.description,
            short_description=product_data.short_description,
            category=product_data.category,
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
            
            # ALWAYS create inventory record for the variant (even if stock is 0)
            from models.catalog.inventories import Inventory, WarehouseLocation
            
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
                from models.catalog.product import ProductImage
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
        return await self.get(db_product.id)

    async def update(
        self,
        product_id: UUID,
        product_data: ProductUpdate,
        user_id: UUID,
        is_admin: bool = False
    ) -> ProductResponse:
        """Update a product and its variants."""
        from models.catalog.inventories import Inventory
        
        logger.info(f"Updating product {product_id} with data: {product_data.dict(exclude_unset=True)}")
        
        query = select(Product).options(
            selectinload(Product.variants).selectinload(ProductVariant.images),
            selectinload(Product.variants).selectinload(ProductVariant.inventory)
        ).where(Product.id == product_id)
        result = await self.db.execute(query)
        product = result.scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        # Check if user is admin (only admins can update products)
        if not is_admin:
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
        return await self.get(product_id)

    async def delete(self, product_id: UUID, user_id: UUID, is_admin: bool = False):
        """Delete a product and all its associated data (variants, inventory, reviews, cart items, wishlist items)."""
        from models.commerce.orders import OrderItem
        
        query = select(Product).where(Product.id == product_id)
        result = await self.db.execute(query)
        product = result.scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        # Check if user is admin (only admins can delete products)
        if not is_admin:
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
