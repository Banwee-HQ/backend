#!/usr/bin/env python3
"""
Seed script to populate database with test products for API testing
"""
import asyncio
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.db import AsyncSessionDB
from core.utils.uuid_utils import uuid7
from datetime import datetime, timezone
from models.catalog.product import Product, ProductVariant, ProductImage
from models.catalog.inventories import Inventory, WarehouseLocation, StockAdjustment
from core.db import db_manager
from core.config import settings

async def seed_products():
    """Create sample products with variants and inventory"""
    # Initialize database
    db_manager.initialize(settings.SQLALCHEMY_DATABASE_URI, settings.ENVIRONMENT == "local")
    
    from core.db import AsyncSessionDB
    async with AsyncSessionDB() as db:
        # Check if products already exist
        result = await db.execute(select(Product).limit(1))
        if result.scalar_one_or_none():
            print("Products already exist, skipping seed")
            return
        
        # Create sample products with full schema support
        products_data = [
            {
                "name": "Organic Ghanaian Cocoa Powder",
                "description": "Premium organic cocoa powder sourced from Ghana's finest cocoa farms. Rich flavor perfect for baking and beverages.",
                "short_description": "Premium organic cocoa powder from Ghana",
                "category": "food",
                "base_price": 24.99,
                "product_metadata": {"origin": "Ghana", "certifications": ["organic", "fair-trade"], "shelf_life_months": 24},
                "variants": [
                    {
                        "sku": "COCO-250G", "name": "250g Bag", "price": 12.99, "quantity": 50,
                        "attributes": {"weight": "250g", "package_type": "bag"},
                        "specifications": {"dimensions": "15x10x5 cm", "weight_kg": 0.25},
                        "dietary_tags": {"vegan": True, "gluten_free": True, "organic": True},
                        "tags": "organic,vegan,gluten-free,baking"
                    },
                    {
                        "sku": "COCO-500G", "name": "500g Bag", "price": 22.99, "quantity": 40,
                        "attributes": {"weight": "500g", "package_type": "bag"},
                        "specifications": {"dimensions": "20x15x8 cm", "weight_kg": 0.5},
                        "dietary_tags": {"vegan": True, "gluten_free": True, "organic": True},
                        "tags": "organic,vegan,gluten-free,baking,value"
                    },
                    {
                        "sku": "COCO-1KG", "name": "1kg Bag", "price": 39.99, "quantity": 30,
                        "attributes": {"weight": "1kg", "package_type": "bag"},
                        "specifications": {"dimensions": "25x20x12 cm", "weight_kg": 1.0},
                        "dietary_tags": {"vegan": True, "gluten_free": True, "organic": True},
                        "tags": "organic,vegan,gluten-free,baking,bulk"
                    },
                ]
            },
            {
                "name": "Shea Butter Moisturizer",
                "description": "Pure African shea butter for deep skin hydration. Natural and unrefined from Ghana and Burkina Faso.",
                "short_description": "Pure African shea butter for deep hydration",
                "category": "beauty",
                "base_price": 18.99,
                "product_metadata": {"origin": "Ghana/Burkina Faso", "skin_types": ["all", "dry", "sensitive"], "usage": ["face", "body", "hair"]},
                "variants": [
                    {
                        "sku": "SHEA-100ML", "name": "100ml Jar", "price": 9.99, "quantity": 60,
                        "attributes": {"volume": "100ml", "container": "jar"},
                        "specifications": {"dimensions": "6x6x5 cm", "weight_kg": 0.12},
                        "dietary_tags": {},
                        "tags": "natural,moisturizer,skincare,travel-size"
                    },
                    {
                        "sku": "SHEA-250ML", "name": "250ml Jar", "price": 18.99, "quantity": 45,
                        "attributes": {"volume": "250ml", "container": "jar"},
                        "specifications": {"dimensions": "8x8x7 cm", "weight_kg": 0.28},
                        "dietary_tags": {},
                        "tags": "natural,moisturizer,skincare,regular"
                    },
                    {
                        "sku": "SHEA-500ML", "name": "500ml Jar", "price": 32.99, "quantity": 25,
                        "attributes": {"volume": "500ml", "container": "jar"},
                        "specifications": {"dimensions": "10x10x9 cm", "weight_kg": 0.55},
                        "dietary_tags": {},
                        "tags": "natural,moisturizer,skincare,family-size"
                    },
                ]
            },
            {
                "name": "Handwoven Kente Cloth",
                "description": "Authentic Ghanaian Kente cloth handwoven by skilled artisans. Traditional patterns with rich cultural significance.",
                "short_description": "Authentic handwoven Ghanaian Kente cloth",
                "category": "fashion",
                "base_price": 89.99,
                "product_metadata": {"origin": "Ghana", "craft": "handwoven", "material": "cotton/silk blend"},
                "variants": [
                    {
                        "sku": "KENTE-STOLE", "name": "Graduation Stole", "price": 45.99, "quantity": 20,
                        "attributes": {"size": "stole", "length": "72 inches"},
                        "specifications": {"dimensions": "180x15 cm", "weight_kg": 0.3},
                        "dietary_tags": {},
                        "tags": "handwoven,traditional,graduation,gift"
                    },
                    {
                        "sku": "KENTE-2YARD", "name": "2 Yards", "price": 89.99, "quantity": 15,
                        "attributes": {"size": "2 yards", "width": "46 inches"},
                        "specifications": {"dimensions": "180x117 cm", "weight_kg": 0.8},
                        "dietary_tags": {},
                        "tags": "handwoven,traditional,ceremonial"
                    },
                    {
                        "sku": "KENTE-4YARD", "name": "4 Yards", "price": 169.99, "quantity": 10,
                        "attributes": {"size": "4 yards", "width": "46 inches"},
                        "specifications": {"dimensions": "360x117 cm", "weight_kg": 1.5},
                        "dietary_tags": {},
                        "tags": "handwoven,traditional,ceremonial,premium"
                    },
                ]
            },
            {
                "name": "Baobab Superfood Powder",
                "description": "Nutrient-rich baobab fruit powder. High in vitamin C, fiber, and antioxidants. Sustainably harvested from African baobab trees.",
                "short_description": "Nutrient-rich African baobab superfood powder",
                "category": "food",
                "base_price": 29.99,
                "product_metadata": {"origin": "Zimbabwe/Malawi", "superfood": True, "health_benefits": ["immune support", "digestive health"]},
                "variants": [
                    {
                        "sku": "BAOBAB-100G", "name": "100g Pouch", "price": 14.99, "quantity": 80,
                        "attributes": {"weight": "100g", "package_type": "pouch"},
                        "specifications": {"dimensions": "12x8x2 cm", "weight_kg": 0.1},
                        "dietary_tags": {"vegan": True, "gluten_free": True, "raw": True, "superfood": True},
                        "tags": "superfood,vegan,gluten-free,immune-boost"
                    },
                    {
                        "sku": "BAOBAB-250G", "name": "250g Pouch", "price": 29.99, "quantity": 50,
                        "attributes": {"weight": "250g", "package_type": "pouch"},
                        "specifications": {"dimensions": "18x12x4 cm", "weight_kg": 0.25},
                        "dietary_tags": {"vegan": True, "gluten_free": True, "raw": True, "superfood": True},
                        "tags": "superfood,vegan,gluten-free,immune-boost,value"
                    },
                    {
                        "sku": "BAOBAB-500G", "name": "500g Pouch", "price": 49.99, "quantity": 30,
                        "attributes": {"weight": "500g", "package_type": "pouch"},
                        "specifications": {"dimensions": "22x16x6 cm", "weight_kg": 0.5},
                        "dietary_tags": {"vegan": True, "gluten_free": True, "raw": True, "superfood": True},
                        "tags": "superfood,vegan,gluten-free,immune-boost,bulk"
                    },
                ]
            },
            {
                "name": "African Black Soap",
                "description": "Traditional African black soap made with natural ingredients like plantain skins, cocoa pod powder, and palm kernel oil. Great for all skin types, especially acne-prone skin.",
                "short_description": "Traditional African black soap for all skin types",
                "category": "beauty",
                "base_price": 12.99,
                "product_metadata": {"origin": "Ghana/Nigeria", "skin_concerns": ["acne", "eczema", "dark spots"], "ph_balanced": True},
                "variants": [
                    {
                        "sku": "BLACKSOAP-1BAR", "name": "Single Bar", "price": 6.99, "quantity": 100,
                        "attributes": {"size": "single", "weight": "150g"},
                        "specifications": {"dimensions": "8x5x3 cm", "weight_kg": 0.15},
                        "dietary_tags": {},
                        "tags": "natural,skincare,acne,traditional"
                    },
                    {
                        "sku": "BLACKSOAP-3PACK", "name": "3-Pack", "price": 18.99, "quantity": 50,
                        "attributes": {"size": "3-pack", "weight": "450g total"},
                        "specifications": {"dimensions": "15x10x4 cm", "weight_kg": 0.45},
                        "dietary_tags": {},
                        "tags": "natural,skincare,acne,traditional,value-pack"
                    },
                    {
                        "sku": "BLACKSOAP-6PACK", "name": "6-Pack", "price": 34.99, "quantity": 30,
                        "attributes": {"size": "6-pack", "weight": "900g total"},
                        "specifications": {"dimensions": "20x15x6 cm", "weight_kg": 0.9},
                        "dietary_tags": {},
                        "tags": "natural,skincare,acne,traditional,bulk-save"
                    },
                ]
            }
        ]
        
        # Create default warehouse location
        location = WarehouseLocation(
            id=uuid7(),
            name="Main Warehouse",
            address="Accra, Ghana",
            description="Primary fulfillment center"
        )
        db.add(location)
        await db.flush()
        
        now = datetime.now(timezone.utc)
        created_variants = 0
        created_images = 0
        
        for product_data in products_data:
            # Create product with all fields
            import re
            slug = re.sub(r'[^\w]+', '-', product_data["name"].lower()).strip('-')
            product = Product(
                id=uuid7(),
                name=product_data["name"],
                slug=slug,
                description=product_data["description"],
                short_description=product_data.get("short_description"),
                category=product_data["category"],
                product_status="active",
                is_featured=True,
                is_bestseller=False,
                published_at=now,
                product_metadata=product_data.get("product_metadata"),
            )
            db.add(product)
            await db.flush()
            
            # Create variants with full attributes
            for idx, var_data in enumerate(product_data["variants"]):
                variant = ProductVariant(
                    id=uuid7(),
                    product_id=product.id,
                    sku=var_data["sku"],
                    name=var_data["name"],
                    base_price=var_data["price"],
                    sale_price=None,
                    availability_status="available",
                    is_active=True,
                    attributes=var_data.get("attributes"),
                    specifications=var_data.get("specifications"),
                    dietary_tags=var_data.get("dietary_tags", {}),
                    tags=var_data.get("tags"),
                    view_count=0,
                    purchase_count=0,
                )
                db.add(variant)
                await db.flush()
                created_variants += 1
                
                # Create inventory with full fields
                inventory = Inventory(
                    id=uuid7(),
                    variant_id=variant.id,
                    location_id=location.id,
                    quantity_available=var_data["quantity"],
                    quantity=var_data["quantity"],
                    low_stock_threshold=10,
                    reorder_point=5,
                    inventory_status="active",
                    last_restocked_at=now,
                    version=0,
                )
                db.add(inventory)
                await db.flush()
                
                # Create stock adjustment record for audit trail
                adjustment = StockAdjustment(
                    id=uuid7(),
                    inventory_id=inventory.id,
                    quantity_change=var_data["quantity"],
                    reason="initial_stock",
                    adjusted_by_user_id=None,
                    notes=f"Initial stock seed for {var_data['sku']}"
                )
                db.add(adjustment)
                
                # Create a primary product image for each variant
                image_url = f"https://cdn.banwee.com/products/{slug}-{idx+1}.jpg"
                product_image = ProductImage(
                    id=uuid7(),
                    variant_id=variant.id,
                    url=image_url,
                    alt_text=f"{product_data['name']} - {var_data['name']}",
                    is_primary=(idx == 0),  # First variant is primary
                    sort_order=idx,
                    format="jpg",
                )
                db.add(product_image)
                created_images += 1
        
        await db.commit()
        print(f"✓ Created {len(products_data)} products with {created_variants} variants")
        print(f"✓ Created {created_images} product images")
        print(f"✓ Created stock adjustment records for audit trail")

if __name__ == "__main__":
    asyncio.run(seed_products())
