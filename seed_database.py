#!/usr/bin/env python3
"""
Database Seeder Script - COMPREHENSIVE
Populates ALL database tables with sample data for testing
"""
import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from passlib.context import CryptContext

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.db import get_db, Base, db_manager
from core.logging import get_structured_logger
from core.config import settings
from enum import Enum

# Import all models
from models.auth.user import User, Address, UserRole, AccountStatus, VerificationStatus, AddressKind
from models.catalog.product import Product, ProductVariant, ProductImage
from models.catalog.inventories import Inventory, WarehouseLocation, StockAdjustment
from models.catalog.review import Review
from models.catalog.wishlist import Wishlist, WishlistItem
from models.commerce.shipping import ShippingMethod
from models.commerce.tax_rates import TaxRate
from models.commerce.promocode import Promocode, DiscountType
from models.commerce.cart import Cart, CartItem
from models.commerce.orders import Order, OrderItem
from models.commerce.payments import PaymentMethod, PaymentType, PaymentProvider, CardBrand
from models.system.contact_message import ContactMessage, MessageStatus, MessagePriority

logger = get_structured_logger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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

# ============================================================================
# SHIPPING METHODS DATA
# ============================================================================
SHIPPING_METHODS = [
    {
        "name": "Standard Shipping",
        "description": "Standard ground shipping with tracking",
        "price": 5.99,
        "estimated_days": 5,
        "is_active": True,
        "carrier": "UPS",
        "tracking_url_template": "https://www.ups.com/track?tracknum={tracking_number}"
    },
    {
        "name": "Express Shipping",
        "description": "2-3 day express delivery",
        "price": 15.99,
        "estimated_days": 2,
        "is_active": True,
        "carrier": "FedEx",
        "tracking_url_template": "https://www.fedex.com/apps/fedextrack/?tracknumbers={tracking_number}"
    },
    {
        "name": "Free Shipping",
        "description": "Free standard shipping on orders over $50",
        "price": 0.00,
        "estimated_days": 7,
        "is_active": True,
        "carrier": "USPS",
        "tracking_url_template": "https://tools.usps.com/go/TrackConfirmAction?tLabels={tracking_number}"
    },
    {
        "name": "Overnight Shipping",
        "description": "Next business day delivery",
        "price": 29.99,
        "estimated_days": 1,
        "is_active": True,
        "carrier": "FedEx",
        "tracking_url_template": "https://www.fedex.com/apps/fedextrack/?tracknumbers={tracking_number}"
    }
]

# ============================================================================
# TAX RATES DATA
# ============================================================================
TAX_RATES = [
    # United States
    {"country_code": "US", "country_name": "United States", "province_code": "CA", "province_name": "California", "tax_rate": 0.0725, "tax_name": "Sales Tax"},
    {"country_code": "US", "country_name": "United States", "province_code": "NY", "province_name": "New York", "tax_rate": 0.08, "tax_name": "Sales Tax"},
    {"country_code": "US", "country_name": "United States", "province_code": "TX", "province_name": "Texas", "tax_rate": 0.0625, "tax_name": "Sales Tax"},
    {"country_code": "US", "country_name": "United States", "province_code": "FL", "province_name": "Florida", "tax_rate": 0.06, "tax_name": "Sales Tax"},
    {"country_code": "US", "country_name": "United States", "province_code": "WA", "province_name": "Washington", "tax_rate": 0.065, "tax_name": "Sales Tax"},
    {"country_code": "US", "country_name": "United States", "province_code": None, "province_name": None, "tax_rate": 0.00, "tax_name": "Federal"},
    # Canada
    {"country_code": "CA", "country_name": "Canada", "province_code": "ON", "province_name": "Ontario", "tax_rate": 0.13, "tax_name": "HST"},
    {"country_code": "CA", "country_name": "Canada", "province_code": "BC", "province_name": "British Columbia", "tax_rate": 0.12, "tax_name": "GST/PST"},
    {"country_code": "CA", "country_name": "Canada", "province_code": "QC", "province_name": "Quebec", "tax_rate": 0.14975, "tax_name": "QST"},
    # UK/EU
    {"country_code": "GB", "country_name": "United Kingdom", "province_code": None, "province_name": None, "tax_rate": 0.20, "tax_name": "VAT"},
    {"country_code": "DE", "country_name": "Germany", "province_code": None, "province_name": None, "tax_rate": 0.19, "tax_name": "VAT"},
    {"country_code": "FR", "country_name": "France", "province_code": None, "province_name": None, "tax_rate": 0.20, "tax_name": "VAT"},
    # African countries
    {"country_code": "GH", "country_name": "Ghana", "province_code": None, "province_name": None, "tax_rate": 0.125, "tax_name": "VAT"},
    {"country_code": "NG", "country_name": "Nigeria", "province_code": None, "province_name": None, "tax_rate": 0.075, "tax_name": "VAT"},
    {"country_code": "ZA", "country_name": "South Africa", "province_code": None, "province_name": None, "tax_rate": 0.15, "tax_name": "VAT"},
    {"country_code": "KE", "country_name": "Kenya", "province_code": None, "province_name": None, "tax_rate": 0.16, "tax_name": "VAT"},
]

# ============================================================================
# PROMOCODES DATA
# ============================================================================
PROMOCODES = [
    {
        "code": "WELCOME20",
        "description": "20% off your first order",
        "discount_type": DiscountType.PERCENTAGE,
        "value": 20.0,
        "minimum_order_amount": 25.00,
        "maximum_discount_amount": 50.00,
        "usage_limit": 1000,
        "is_active": True,
        "valid_from": datetime.now(timezone.utc) - timedelta(days=30),
        "valid_until": datetime.now(timezone.utc) + timedelta(days=365)
    },
    {
        "code": "ORGANIC10",
        "description": "$10 off orders over $75",
        "discount_type": DiscountType.FIXED,
        "value": 10.0,
        "minimum_order_amount": 75.00,
        "maximum_discount_amount": 10.00,
        "usage_limit": 500,
        "is_active": True,
        "valid_from": datetime.now(timezone.utc) - timedelta(days=10),
        "valid_until": datetime.now(timezone.utc) + timedelta(days=90)
    },
    {
        "code": "FREESHIP",
        "description": "Free shipping on any order",
        "discount_type": DiscountType.FIXED,
        "value": 5.99,
        "minimum_order_amount": 0.00,
        "maximum_discount_amount": 5.99,
        "usage_limit": 200,
        "is_active": True,
        "valid_from": datetime.now(timezone.utc),
        "valid_until": datetime.now(timezone.utc) + timedelta(days=30)
    },
    {
        "code": "BULK15",
        "description": "15% off orders over $100",
        "discount_type": DiscountType.PERCENTAGE,
        "value": 15.0,
        "minimum_order_amount": 100.00,
        "maximum_discount_amount": 75.00,
        "usage_limit": 300,
        "is_active": True,
        "valid_from": datetime.now(timezone.utc),
        "valid_until": datetime.now(timezone.utc) + timedelta(days=60)
    }
]

# ============================================================================
# CONTACT MESSAGES DATA
# ============================================================================
CONTACT_MESSAGES = [
    {
        "name": "John Smith",
        "email": "john.smith@example.com",
        "subject": "Question about fonio millet",
        "message": "Hi, I'm interested in buying fonio millet in bulk. Do you offer wholesale pricing for orders over 50kg?",
        "status": MessageStatus.NEW,
        "priority": MessagePriority.MEDIUM
    },
    {
        "name": "Sarah Johnson",
        "email": "sarah.j@example.com",
        "subject": "Shipping to Canada",
        "message": "Do you ship to Canada? What are the shipping costs and delivery times?",
        "status": MessageStatus.IN_PROGRESS,
        "priority": MessagePriority.HIGH
    },
    {
        "name": "Michael Brown",
        "email": "mbrown@example.com",
        "subject": "Product availability",
        "message": "When will the shea butter be back in stock? I've been waiting for the 500ml size.",
        "status": MessageStatus.RESOLVED,
        "priority": MessagePriority.LOW
    },
    {
        "name": "Emma Wilson",
        "email": "emma.w@example.com",
        "subject": "Order cancellation",
        "message": "I need to cancel my order #12345. Please confirm the cancellation.",
        "status": MessageStatus.NEW,
        "priority": MessagePriority.URGENT
    },
    {
        "name": "David Lee",
        "email": "david.lee@example.com",
        "subject": "Payment issue",
        "message": "My credit card was charged twice for order #12346. Can you help with a refund?",
        "status": MessageStatus.IN_PROGRESS,
        "priority": MessagePriority.HIGH
    }
]

# ============================================================================
# SAMPLE USERS DATA
# ============================================================================
SAMPLE_USERS = [
    {
        "email": "customer1@example.com",
        "firstname": "Alice",
        "lastname": "Johnson",
        "password": "TestPass123!",
        "role": UserRole.CUSTOMER,
        "account_status": AccountStatus.ACTIVE,
        "verification_status": VerificationStatus.VERIFIED,
        "country": "US",
        "phone": "+1234567890"
    },
    {
        "email": "customer2@example.com",
        "firstname": "Bob",
        "lastname": "Williams",
        "password": "TestPass123!",
        "role": UserRole.CUSTOMER,
        "account_status": AccountStatus.ACTIVE,
        "verification_status": VerificationStatus.VERIFIED,
        "country": "CA",
        "phone": "+14165551234"
    },
    {
        "email": "manager@banwee.com",
        "firstname": "Manager",
        "lastname": "User",
        "password": "AdminPass123!",
        "role": UserRole.MANAGER,
        "account_status": AccountStatus.ACTIVE,
        "verification_status": VerificationStatus.VERIFIED,
        "country": "GH",
        "phone": "+233123456789"
    }
]

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
    """Create admin user with proper password hashing"""
    # Check if admin user exists
    result = await db.execute(
        text("SELECT id FROM users WHERE email = :email"),
        {"email": "admin@banwee.com"}
    )
    existing_id = result.scalar()
    
    if existing_id:
        # Fetch the existing user object
        result = await db.execute(
            select(User).where(User.id == existing_id)
        )
        existing_admin = result.scalar_one_or_none()
        logger.info("✅ Admin user already exists: admin@banwee.com")
        return existing_admin

    # Hash password properly
    hashed_password = pwd_context.hash("AdminPass123!")

    admin_user = User(
        id=uuid4(),
        email="admin@banwee.com",
        firstname="Admin",
        lastname="User",
        hashed_password=hashed_password,
        account_status=AccountStatus.ACTIVE,
        verification_status=VerificationStatus.VERIFIED,
        role=UserRole.ADMIN,
        country="GH",
        phone="+233123456789",
        language="en",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

    db.add(admin_user)
    await db.flush()  # Get user ID

    # Add default address for admin
    admin_address = Address(
        id=uuid4(),
        user_id=admin_user.id,
        street="123 Admin Street",
        city="Accra",
        state="Greater Accra",
        country="GH",
        post_code="00233",
        kind=AddressKind.SHIPPING,
        is_default=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db.add(admin_address)
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

async def seed_shipping_methods(db: AsyncSession):
    """Seed shipping methods"""
    logger.info("📦 Seeding shipping methods...")
    
    for method_data in SHIPPING_METHODS:
        # Check if exists
        result = await db.execute(
            select(ShippingMethod).where(ShippingMethod.name == method_data["name"])
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            method = ShippingMethod(
                id=uuid4(),
                name=method_data["name"],
                description=method_data["description"],
                price=method_data["price"],
                estimated_days=method_data["estimated_days"],
                is_active=method_data["is_active"],
                carrier=method_data.get("carrier"),
                tracking_url_template=method_data.get("tracking_url_template"),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db.add(method)
            logger.info(f"  ✅ Created shipping method: {method.name}")
        else:
            # Update existing
            existing.price = method_data["price"]
            existing.estimated_days = method_data["estimated_days"]
            existing.is_active = method_data["is_active"]
            existing.updated_at = datetime.now(timezone.utc)
            logger.info(f"  🔄 Updated shipping method: {existing.name}")
    
    await db.commit()
    logger.info(f"✅ Shipping methods seeded: {len(SHIPPING_METHODS)}")

async def seed_tax_rates(db: AsyncSession):
    """Seed tax rates"""
    logger.info("💰 Seeding tax rates...")
    
    for tax_data in TAX_RATES:
        # Check if exists (by country + province)
        result = await db.execute(
            select(TaxRate).where(
                TaxRate.country_code == tax_data["country_code"],
                TaxRate.province_code == tax_data["province_code"]
            )
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            tax_rate = TaxRate(
                id=uuid4(),
                country_code=tax_data["country_code"],
                country_name=tax_data["country_name"],
                province_code=tax_data.get("province_code"),
                province_name=tax_data.get("province_name"),
                tax_rate=tax_data["tax_rate"],
                tax_name=tax_data["tax_name"],
                is_active=True,
                effective_date=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db.add(tax_rate)
            location = f"{tax_data['country_code']}"
            if tax_data.get('province_code'):
                location += f"-{tax_data['province_code']}"
            logger.info(f"  ✅ Created tax rate: {location} @ {tax_data['tax_rate']*100}%")
    
    await db.commit()
    logger.info(f"✅ Tax rates seeded: {len(TAX_RATES)}")

async def seed_promocodes(db: AsyncSession):
    """Seed promocodes"""
    logger.info("🎟️ Seeding promocodes...")
    
    for promo_data in PROMOCODES:
        # Check if exists
        result = await db.execute(
            select(Promocode).where(Promocode.code == promo_data["code"])
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            promocode = Promocode(
                id=uuid4(),
                code=promo_data["code"],
                description=promo_data["description"],
                discount_type=promo_data["discount_type"],
                value=promo_data["value"],
                minimum_order_amount=promo_data.get("minimum_order_amount"),
                maximum_discount_amount=promo_data.get("maximum_discount_amount"),
                usage_limit=promo_data.get("usage_limit"),
                used_count=0,
                is_active=promo_data["is_active"],
                valid_from=promo_data.get("valid_from"),
                valid_until=promo_data.get("valid_until"),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db.add(promocode)
            logger.info(f"  ✅ Created promocode: {promocode.code}")
        else:
            # Update validity
            existing.is_active = promo_data["is_active"]
            existing.valid_until = promo_data.get("valid_until")
            existing.updated_at = datetime.now(timezone.utc)
            logger.info(f"  🔄 Updated promocode: {existing.code}")
    
    await db.commit()
    logger.info(f"✅ Promocodes seeded: {len(PROMOCODES)}")

async def seed_contact_messages(db: AsyncSession):
    """Seed contact messages"""
    logger.info("📧 Seeding contact messages...")
    
    for msg_data in CONTACT_MESSAGES:
        # Check if exists (by email + subject)
        result = await db.execute(
            select(ContactMessage).where(
                ContactMessage.email == msg_data["email"],
                ContactMessage.subject == msg_data["subject"]
            )
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            message = ContactMessage(
                id=uuid4(),
                name=msg_data["name"],
                email=msg_data["email"],
                subject=msg_data["subject"],
                message=msg_data["message"],
                status=msg_data["status"],
                priority=msg_data["priority"],
                created_at=datetime.now(timezone.utc) - timedelta(days=1),
                updated_at=datetime.now(timezone.utc)
            )
            db.add(message)
            logger.info(f"  ✅ Created contact message: {message.subject}")
    
    await db.commit()
    logger.info(f"✅ Contact messages seeded: {len(CONTACT_MESSAGES)}")

async def create_sample_users(db: AsyncSession):
    """Create sample users with addresses"""
    logger.info("👥 Creating sample users...")
    
    created_users = []
    
    for user_data in SAMPLE_USERS:
        # Check if user exists - use raw SQL to avoid schema issues
        result = await db.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": user_data["email"]}
        )
        existing_id = result.scalar()
        
        existing = None
        if existing_id:
            result = await db.execute(
                select(User).where(User.id == existing_id)
            )
            existing = result.scalar_one_or_none()
        
        if not existing:
            # Hash password
            hashed_password = pwd_context.hash(user_data["password"])
            
            user = User(
                id=uuid4(),
                email=user_data["email"],
                firstname=user_data["firstname"],
                lastname=user_data["lastname"],
                hashed_password=hashed_password,
                role=user_data["role"],
                account_status=user_data["account_status"],
                verification_status=user_data["verification_status"],
                country=user_data.get("country"),
                phone=user_data.get("phone"),
                language="en",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db.add(user)
            await db.flush()  # Get user ID
            
            created_users.append(user)
            logger.info(f"  ✅ Created user: {user.email} ({user.role.value})")
            
            # Add sample address for the user
            address = Address(
                id=uuid4(),
                user_id=user.id,
                street=f"123 {user.firstname} Street",
                city="Sample City",
                state="CA" if user.country == "US" else "ON" if user.country == "CA" else "Accra",
                country=user.country or "US",
                post_code="12345" if user.country == "US" else "A1B2C3" if user.country == "CA" else "00233",
                kind=AddressKind.SHIPPING,
                is_default=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db.add(address)
            logger.info(f"    📍 Added address for: {user.email}")
        else:
            created_users.append(existing)
            logger.info(f"  🔄 User already exists: {existing.email}")
    
    await db.commit()
    logger.info(f"✅ Sample users created: {len(created_users)}")
    return created_users

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
        
        # PostgreSQL: create tables with schemas
        async with db_manager.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        async for db in get_db():
            # Clear existing data in correct order (respecting FK constraints)
            logger.info("🗑️ Clearing existing data...")
            
            # Commerce tables (dependent on users/products)
            await db.execute(text("DELETE FROM cart_items"))
            await db.execute(text("DELETE FROM carts"))
            await db.execute(text("DELETE FROM order_items"))
            await db.execute(text("DELETE FROM orders"))
            await db.execute(text("DELETE FROM payment_methods"))
            await db.execute(text("DELETE FROM wishlist_items"))
            await db.execute(text("DELETE FROM wishlists"))
            await db.execute(text("DELETE FROM reviews"))
            
            # Catalog tables
            await db.execute(text("DELETE FROM product_images"))
            await db.execute(text("DELETE FROM inventory"))
            await db.execute(text("DELETE FROM stock_adjustments"))
            await db.execute(text("DELETE FROM product_variants"))
            await db.execute(text("DELETE FROM products"))
            await db.execute(text("DELETE FROM warehouse_locations"))
            
            # Commerce config tables
            await db.execute(text("DELETE FROM promocodes"))
            await db.execute(text("DELETE FROM tax_rates"))
            await db.execute(text("DELETE FROM shipping_methods"))
            
            # System tables
            await db.execute(text("DELETE FROM contact_messages"))
            
            # Auth tables (last - many things depend on users)
            await db.execute(text("DELETE FROM addresses"))
            await db.execute(text("DELETE FROM users"))
            
            await db.commit()
            logger.info("✅ Database cleared")
            
            # Seed new data in correct order
            logger.info("\n📦 Seeding data...")
            
            # 1. Auth & Users first (other tables depend on users)
            admin_user = await create_admin_user(db)
            sample_users = await create_sample_users(db)
            
            # 2. Commerce configuration (no dependencies)
            await seed_shipping_methods(db)
            await seed_tax_rates(db)
            await seed_promocodes(db)
            
            # 3. System data
            await seed_contact_messages(db)
            
            # 4. Catalog data (products, inventory)
            await seed_products(db)
            
            break  # Only need one session
        
        logger.info("🎉 Database seeding completed successfully!")
        print("\n" + "="*60)
        print("🎉 DATABASE SEEDING COMPLETED!")
        print("="*60)
        print("\n📧 USERS:")
        print("   Admin:      admin@banwee.com / AdminPass123!")
        print("   Manager:    manager@banwee.com / AdminPass123!")
        print("   Customer 1: customer1@example.com / TestPass123!")
        print("   Customer 2: customer2@example.com / TestPass123!")
        print(f"\n🛍️  PRODUCTS: {len(PRODUCTS)} products with {sum(len(p['variants']) for p in PRODUCTS)} variants")
        print(f"📦 SHIPPING: {len(SHIPPING_METHODS)} methods")
        print(f"💰 TAX RATES: {len(TAX_RATES)} rates")
        print(f"🎟️  PROMOCODES: {len(PROMOCODES)} codes")
        print(f"📧 CONTACT MESSAGES: {len(CONTACT_MESSAGES)} messages")
        print("="*60)
        
    except Exception as e:
        logger.error(f"❌ Database seeding failed: {e}")
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    asyncio.run(main())
