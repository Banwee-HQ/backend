#!/usr/bin/env python3
"""
Database Seeder Script
Populates database with products, variants, images, and admin user
"""
import asyncio
import sys
import os
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.db import get_db, BaseModel, db_manager
from models.catalog.product import Product, ProductVariant, ProductImage
from models.catalog.inventories import Inventory, WarehouseLocation
from models.auth.user import User
from core.logging import get_structured_logger
from enum import Enum

# Product Categories Enum
class ProductCategory(str, Enum):
    GRAINS_CEREALS_BEANS = "Grains, Cereals & Beans"
    FRUITS_VEGETABLES = "Fruits & Vegetables"
    MEAT_POULTRY_SEAFOOD = "Meat, Poultry & Seafood"
    DAIRY_EGGS_FATS = "Dairy, Eggs & Fats"
    SPICES_HERBS_SEASONINGS = "Spices, Herbs & Seasonings"
    PANTRY_SWEETENERS = "Pantry & Sweeteners"
    NUTS_SEEDS_SNACKS = "Nuts, Seeds & Snacks"  
    BEVERAGES_TEA_COFFEE = "Beverages, Tea & Coffee"
    BAKERY_PREPARED_FOODS = "Bakery & Prepared Foods"
    FIBERS_INDUSTRIAL_CROPS = "Fibers & Industrial Crops"

logger = get_structured_logger(__name__)

# Sample data for African organic products
PRODUCTS = [
    {
        "name": "Premium Fonio Millet",
        "slug": "premium-fonio-millet",
        "description": "Traditional West African fonio millet, organically grown in Ghana. This ancient grain is naturally gluten-free, rich in essential amino acids, and cooks in just 3 minutes. Perfect for healthy breakfast porridges and side dishes.",
        "short_description": "Organic fonio millet from Ghana - naturally gluten-free",
        "category": ProductCategory.GRAINS_CEREALS_BEANS,
        "product_status": "active",
        "is_featured": True,
        "is_bestseller": False,
        "variants": [
            {
                "name": "Premium Fonio - 500g",
                "sku": "FON-001-500",
                "base_price": 12.99,
                "sale_price": 10.99,
                "attributes": {"size": "500g", "grade": "premium"},
                "specifications": {"origin": "Ghana", "gluten_free": True, "cooking_time": "3 minutes"},
                "dietary_tags": "gluten-free,vegan,organic",
                "tags": "grain,millet,gluten-free,organic",
                "inventory_quantity": 100,
                "low_stock_threshold": 20,
                "images": [
                    {
                        "url": "https://images.unsplash.com/photo-1546788233-0b3d4b5a5b5?w=600",
                        "alt_text": "Premium Fonio Millet package",
                        "is_primary": True
                    },
                    {
                        "url": "https://images.unsplash.com/photo-1544787141-e3b5c8f7d7a?w=600",
                        "alt_text": "Fonio millet cooking",
                        "is_primary": False
                    }
                ]
            },
            {
                "name": "Premium Fonio - 1kg",
                "sku": "FON-001-1000",
                "base_price": 22.99,
                "sale_price": 19.99,
                "attributes": {"size": "1kg", "grade": "premium"},
                "specifications": {"origin": "Ghana", "gluten_free": True, "cooking_time": "3 minutes"},
                "dietary_tags": "gluten-free,vegan,organic",
                "tags": "grain,millet,gluten-free,organic,bulk",
                "inventory_quantity": 50,
                "low_stock_threshold": 10,
                "images": []
            }
        ]
    },
    {
        "name": "Grains of Paradise Selim Pepper",
        "slug": "grains-paradise-selim-pepper",
        "description": "Authentic Selim pepper from historic Grains of Paradise region. This complex, aromatic spice offers a unique flavor profile with citrusy, floral, and slightly spicy notes. Perfect for traditional African stews and modern fusion cuisine.",
        "short_description": "Premium Selim pepper with complex citrusy notes",
        "category": ProductCategory.SPICES_HERBS_SEASONINGS,
        "product_status": "active",
        "is_featured": True,
        "is_bestseller": True,
        "variants": [
            {
                "name": "Selim Pepper - Whole 100g",
                "sku": "PEP-002-100",
                "base_price": 8.99,
                "attributes": {"form": "whole", "size": "100g"},
                "specifications": {"origin": "Grains of Paradise", "heat_level": "medium", "flavor_notes": "citrusy,floral"},
                "dietary_tags": "vegan,organic,gluten-free",
                "tags": "pepper,selim,spice,african",
                "inventory_quantity": 75,
                "low_stock_threshold": 15,
                "images": [
                    {
                        "url": "https://images.unsplash.com/photo-1532339414262-c6e9e6c5d3c?w=600",
                        "alt_text": "Selim pepper whole grains",
                        "is_primary": True
                    }
                ]
            },
            {
                "name": "Selim Pepper - Ground 100g",
                "sku": "PEP-002-100G",
                "base_price": 9.99,
                "attributes": {"form": "ground", "size": "100g"},
                "specifications": {"origin": "Grains of Paradise", "heat_level": "medium", "flavor_notes": "citrusy,floral"},
                "dietary_tags": "vegan,organic,gluten-free",
                "tags": "pepper,selim,spice,african,ground",
                "inventory_quantity": 60,
                "low_stock_threshold": 12,
                "images": []
            }
        ]
    },
    {
        "name": "Raw Ghanaian Shea Butter",
        "slug": "raw-ghanaian-shea-butter",
        "description": "100% pure, unrefined shea butter from Ghanaian women's cooperatives. This premium quality butter is rich in vitamins A and E, perfect for skin care, hair care, and cooking. Ethically sourced and sustainably produced.",
        "short_description": "Pure unrefined shea butter from Ghana",
        "category": ProductCategory.NUTS_SEEDS_SNACKS,
        "product_status": "active",
        "is_featured": False,
        "is_bestseller": True,
        "variants": [
            {
                "name": "Raw Shea Butter - 200ml",
                "sku": "SHEA-003-200",
                "base_price": 15.99,
                "attributes": {"size": "200ml", "grade": "raw", "form": "butter"},
                "specifications": {"origin": "Ghana", "purity": "100%", "vitamins": "A,E"},
                "dietary_tags": "vegan,organic,cruelty-free",
                "tags": "shea,butter,skincare,raw,ghana",
                "inventory_quantity": 80,
                "low_stock_threshold": 16,
                "images": [
                    {
                        "url": "https://images.unsplash.com/photo-1572563362249-9b5d1d8d5b8?w=600",
                        "alt_text": "Raw shea butter container",
                        "is_primary": True
                    }
                ]
            },
            {
                "name": "Raw Shea Butter - 500ml",
                "sku": "SHEA-003-500",
                "base_price": 34.99,
                "attributes": {"size": "500ml", "grade": "raw", "form": "butter"},
                "specifications": {"origin": "Ghana", "purity": "100%", "vitamins": "A,E"},
                "dietary_tags": "vegan,organic,cruelty-free",
                "tags": "shea,butter,skincare,raw,ghana,bulk",
                "inventory_quantity": 40,
                "low_stock_threshold": 8,
                "images": []
            }
        ]
    },
    {
        "name": "Sun-Dried Mango Slices",
        "slug": "sun-dried-mango-slices",
        "description": "Naturally sun-dried Ghanaian mango slices, free from preservatives and additives. These sweet, chewy treats retain their natural vitamins and minerals. Perfect for snacking, baking, or adding to cereals.",
        "short_description": "Natural sun-dried mango slices from Ghana",
        "category": ProductCategory.FRUITS_VEGETABLES,
        "product_status": "active",
        "is_featured": True,
        "is_bestseller": False,
        "variants": [
            {
                "name": "Mango Slices - 250g",
                "sku": "MANGO-004-250",
                "base_price": 7.99,
                "sale_price": 6.99,
                "attributes": {"size": "250g", "form": "slices", "drying_method": "sun-dried"},
                "specifications": {"origin": "Ghana", "preservatives": "none", "vitamins": "A,C"},
                "dietary_tags": "vegan,organic,gluten-free,no-preservatives",
                "tags": "mango,dried,fruit,snack,ghana",
                "inventory_quantity": 120,
                "low_stock_threshold": 24,
                "images": [
                    {
                        "url": "https://images.unsplash.com/photo-1553279760-8148bd0c69cf?w=600",
                        "alt_text": "Sun-dried mango slices",
                        "is_primary": True
                    }
                ]
            },
            {
                "name": "Mango Slices - 500g",
                "sku": "MANGO-004-500",
                "base_price": 14.99,
                "sale_price": 12.99,
                "attributes": {"size": "500g", "form": "slices", "drying_method": "sun-dried"},
                "specifications": {"origin": "Ghana", "preservatives": "none", "vitamins": "A,C"},
                "dietary_tags": "vegan,organic,gluten-free,no-preservatives",
                "tags": "mango,dried,fruit,snack,ghana,bulk",
                "inventory_quantity": 60,
                "low_stock_threshold": 12,
                "images": []
            }
        ]
    },
    {
        "name": "Premium Rooibos Tea",
        "slug": "premium-rooibos-tea",
        "description": "Premium grade rooibos tea from South Africa's Cederberg mountains. This naturally caffeine-free herbal tea offers a smooth, slightly sweet flavor with earthy notes. Rich in antioxidants and minerals.",
        "short_description": "Premium caffeine-free rooibos from South Africa",
        "category": ProductCategory.BEVERAGES_TEA_COFFEE,
        "product_status": "active",
        "is_featured": True,
        "is_bestseller": True,
        "variants": [
            {
                "name": "Rooibos Tea Bags - 20 count",
                "sku": "ROO-005-20",
                "base_price": 11.99,
                "attributes": {"form": "tea_bags", "count": 20, "bag_weight": "2g"},
                "specifications": {"origin": "South Africa", "caffeine_free": True, "antioxidants": "high"},
                "dietary_tags": "vegan,organic,caffeine-free,gluten-free",
                "tags": "rooibos,tea,herbal,south-africa",
                "inventory_quantity": 90,
                "low_stock_threshold": 18,
                "images": [
                    {
                        "url": "https://images.unsplash.com/photo-1544788209-7e3d9c8f8d7?w=600",
                        "alt_text": "Rooibos tea bags in box",
                        "is_primary": True
                    }
                ]
            },
            {
                "name": "Rooibos Loose Leaf - 100g",
                "sku": "ROO-005-100",
                "base_price": 16.99,
                "attributes": {"form": "loose_leaf", "weight": "100g"},
                "specifications": {"origin": "South Africa", "caffeine_free": True, "antioxidants": "high"},
                "dietary_tags": "vegan,organic,caffeine-free,gluten-free",
                "tags": "rooibos,tea,herbal,south-africa,loose-leaf",
                "inventory_quantity": 70,
                "low_stock_threshold": 14,
                "images": []
            }
        ]
    }
]

async def create_admin_user(db: AsyncSession) -> User:
    """Create admin user"""
    # Check if admin user exists
    result = await db.execute(
        select(User).where(User.email == "admin@banwee.com")
    )
    existing_admin = result.scalar_one_or_none()
    
    if existing_admin:
        logger.info("Admin user already exists")
        return existing_admin
    
    admin_user = User(
        id=uuid4(),
        email="admin@banwee.com",
        firstname="Admin",
        lastname="User",
        hashed_password="$2b$12$example",  # Change this in production!
        account_status="active",  # Use account_status instead of is_active
        verification_status="verified",  # Use verification_status instead of is_verified
        role="admin",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    
    db.add(admin_user)
    await db.commit()
    logger.info("✅ Created admin user: admin@banwee.com")
    return admin_user

async def seed_products(db: AsyncSession):
    """Seed products with variants and images"""
    logger.info("🛍️ Seeding products (idempotent)...")

    # Ensure default warehouse location exists (idempotent)
    result = await db.execute(
        select(WarehouseLocation).where(WarehouseLocation.name == "Main Warehouse")
    )
    # Use scalars().first() to tolerate duplicates and return the first match
    default_location = result.scalars().first()
    if not default_location:
        default_location = WarehouseLocation(
            id=uuid4(),
            name="Main Warehouse",
            address="123 Main St, Accra, Ghana",
            description="Primary warehouse for all products"
        )
        db.add(default_location)
        await db.flush()

    for product_data in PRODUCTS:
        # Load existing product (with variants) if present
        existing = await db.execute(
            select(Product).where(Product.slug == product_data["slug"]).options(selectinload(Product.variants).selectinload(ProductVariant.images))
        )
        product = existing.scalar_one_or_none()

        if not product:
            product = Product(
                id=uuid4(),
                name=product_data["name"],
                slug=product_data["slug"],
                description=product_data.get("description"),
                short_description=product_data.get("short_description"),
                category=str(product_data.get("category")) if product_data.get("category") else None,
                product_status=product_data.get("product_status", "active"),
                is_featured=product_data.get("is_featured", False),
                is_bestseller=product_data.get("is_bestseller", False),
                rating_average=4.5,
                rating_count=25,
                review_count=20,
                published_at=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db.add(product)
            await db.flush()
            logger.info(f"✅ Created product: {product.name}")
        else:
            # Update mutable fields for existing product
            product.name = product_data.get("name", product.name)
            product.description = product_data.get("description", product.description)
            product.short_description = product_data.get("short_description", product.short_description)
            product.category = str(product_data.get("category")) if product_data.get("category") else product.category
            product.product_status = product_data.get("product_status", product.product_status)
            product.is_featured = product_data.get("is_featured", product.is_featured)
            product.is_bestseller = product_data.get("is_bestseller", product.is_bestseller)
            product.updated_at = datetime.now(timezone.utc)

        # Process variants
        for variant_data in product_data.get("variants", []):
            # Normalize dietary tags to JSON list
            dietary_tags = variant_data.get("dietary_tags", [])
            if isinstance(dietary_tags, str):
                dietary_list = [t.strip() for t in dietary_tags.split(",") if t.strip()]
            else:
                dietary_list = dietary_tags

            # Find existing variant by SKU
            existing_v = await db.execute(
                select(ProductVariant).where(ProductVariant.sku == variant_data["sku"]).options(selectinload(ProductVariant.images), selectinload(ProductVariant.inventory))
            )
            variant = existing_v.scalar_one_or_none()

            if not variant:
                variant = ProductVariant(
                    id=uuid4(),
                    product_id=product.id,
                    name=variant_data.get("name"),
                    sku=variant_data.get("sku"),
                    base_price=variant_data.get("base_price", 0.0),
                    sale_price=variant_data.get("sale_price"),
                    attributes=variant_data.get("attributes", {}),
                    specifications=variant_data.get("specifications", {}),
                    dietary_tags=dietary_list,
                    tags=variant_data.get("tags", ""),
                    availability_status=variant_data.get("availability_status", "available"),
                    view_count=0,
                    purchase_count=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                db.add(variant)
                await db.flush()
                logger.info(f"  ➕ Created variant: {variant.sku}")
            else:
                # Update existing variant
                variant.name = variant_data.get("name", variant.name)
                variant.base_price = variant_data.get("base_price", variant.base_price)
                variant.sale_price = variant_data.get("sale_price", variant.sale_price)
                variant.attributes = variant_data.get("attributes", variant.attributes or {})
                variant.specifications = variant_data.get("specifications", variant.specifications or {})
                variant.dietary_tags = dietary_list if dietary_list else variant.dietary_tags
                variant.tags = variant_data.get("tags", variant.tags)
                variant.availability_status = variant_data.get("availability_status", variant.availability_status)
                variant.updated_at = datetime.now(timezone.utc)

            # Inventory (unique per variant)
            inv_q = await db.execute(select(Inventory).where(Inventory.variant_id == variant.id))
            existing_inv = inv_q.scalar_one_or_none()
            if existing_inv:
                existing_inv.quantity_available = variant_data.get("inventory_quantity", existing_inv.quantity_available)
                existing_inv.low_stock_threshold = variant_data.get("low_stock_threshold", existing_inv.low_stock_threshold)
                existing_inv.last_restocked_at = datetime.now(timezone.utc)
                existing_inv.updated_at = datetime.now(timezone.utc)
            else:
                new_inv = Inventory(
                    id=uuid4(),
                    variant_id=variant.id,
                    location_id=default_location.id,
                    quantity_available=variant_data.get("inventory_quantity", 0),
                    low_stock_threshold=variant_data.get("low_stock_threshold", 10),
                    inventory_status="active",
                    last_restocked_at=datetime.now(timezone.utc),
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                db.add(new_inv)
                await db.flush()

            # Images: create if missing, update if present; ensure one primary
            images = variant_data.get("images", [])
            sort_order = 1
            for img_data in images:
                img_url = img_data.get("url")
                # attempt to infer format
                fmt = None
                try:
                    ext = os.path.splitext(img_url.split("?")[0])[1].lower().lstrip('.')
                    if ext in ("jpg", "jpeg"):
                        fmt = "jpg"
                    elif ext in ("png",):
                        fmt = "png"
                    elif ext in ("webp",):
                        fmt = "webp"
                except Exception:
                    fmt = None

                img_q = await db.execute(
                    select(ProductImage).where(ProductImage.variant_id == variant.id, ProductImage.url == img_url)
                )
                existing_img = img_q.scalar_one_or_none()
                is_primary = bool(img_data.get("is_primary", False))

                if existing_img:
                    existing_img.alt_text = img_data.get("alt_text", existing_img.alt_text)
                    existing_img.is_primary = is_primary
                    existing_img.sort_order = sort_order
                    existing_img.format = fmt or existing_img.format
                else:
                    new_img = ProductImage(
                        id=uuid4(),
                        variant_id=variant.id,
                        url=img_url,
                        alt_text=img_data.get("alt_text"),
                        is_primary=is_primary,
                        sort_order=sort_order,
                        format=fmt,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc)
                    )
                    db.add(new_img)

                # If this image is primary, unset other primary flags for this variant
                if is_primary:
                    await db.execute(
                        text("UPDATE product_images SET is_primary = false WHERE variant_id = :vid AND url != :url"),
                        {"vid": str(variant.id), "url": img_url}
                    )

                sort_order += 1

        # Commit per-product to keep transactions bounded and idempotent
        await db.commit()
        logger.info(f"✅ Upserted product: {product.name} ({product.slug}) with {len(product_data.get('variants', []))} variants")

    logger.info(f"✅ Processed {len(PRODUCTS)} products")

async def main():
    """Main seeder function"""
    logger.info("🚀 Starting database seeder...")
    
    try:
        # Initialize database manager first
        from core.config import settings
        db_manager.initialize(settings.SQLALCHEMY_DATABASE_URI, settings.ENVIRONMENT == "local")
        
        # Create all tables using database manager
        if not db_manager.engine:
            logger.error("❌ Database manager failed to initialize.")
            return
            
        async with db_manager.engine.begin() as conn:
            await conn.run_sync(BaseModel.metadata.create_all)
        
        async for db in get_db():
            # Clear existing data
            logger.info("🗑️ Clearing existing data...")
            await db.execute(text("DELETE FROM product_images"))
            await db.execute(text("DELETE FROM inventory"))
            await db.execute(text("DELETE FROM product_variants"))
            await db.execute(text("DELETE FROM products"))
            await db.commit()
            logger.info("✅ Database cleared")
            
            # Seed new data
            await create_admin_user(db)
            await seed_products(db)
            break  # Only need one session
        
        logger.info("🎉 Database seeding completed successfully!")
        print("\n🎉 Database seeding completed!")
        print("📧 Admin User: admin@banwee.com")
        print("🔑 Admin Password: example (CHANGE IN PRODUCTION!)")
        print(f"🛍️  Created {len(PRODUCTS)} products")
        print(f"📦 Total variants: {sum(len(p['variants']) for p in PRODUCTS)}")
        
    except Exception as e:
        logger.error(f"❌ Database seeding failed: {e}")
        print(f"❌ Error: {e}")
        # Do not call sys.exit from inside the async context (causes aclose() errors).
        # Re-raise so the error propagates and the event loop can close cleanly.
        raise

if __name__ == "__main__":
    asyncio.run(main())
