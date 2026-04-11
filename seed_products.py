#!/usr/bin/env python3
"""
Seed script — populates the database with products, shipping methods,
tax rates, and an admin user ready for API testing.
"""
import asyncio
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from core.config import settings
from core.db import db_manager
from sqlalchemy import select, text
from core.utils.uuid_utils import uuid7
from core.utils.encryption import PasswordManager

from models.accounts.user import User
from models.catalog.product import Product, ProductVariant, ProductImage
from models.catalog.review import Review
from models.catalog.inventories import Inventory, WarehouseLocation, StockAdjustment
from models.commerce.shipping import ShippingMethod
from models.commerce.tax_rates import TaxRate


# ─────────────────────────────────────────────
# Product catalogue data
# ─────────────────────────────────────────────
PRODUCTS = [
    {
        "name": "Organic Ghanaian Cocoa Powder",
        "slug": "organic-ghanaian-cocoa-powder",
        "description": "Premium organic cocoa powder sourced from Ghana's finest cocoa farms. Rich flavour perfect for baking and beverages.",
        "short_description": "Premium organic cocoa powder from Ghana",
        "category": "food",
        "product_metadata": {"origin": "Ghana", "certifications": ["organic", "fair-trade"], "shelf_life_months": 24},
        "variants": [
            {"sku": "COCO-250G", "name": "250g Bag",  "base_price": 12.99, "quantity": 50,
             "attributes": {"weight": "250g", "package_type": "bag"},
             "specifications": {"dimensions": "15x10x5 cm", "weight_kg": 0.25},
             "dietary_tags": {"vegan": True, "gluten_free": True, "organic": True},
             "tags": "organic,vegan,gluten-free,baking"},
            {"sku": "COCO-500G", "name": "500g Bag",  "base_price": 22.99, "quantity": 40,
             "attributes": {"weight": "500g", "package_type": "bag"},
             "specifications": {"dimensions": "20x15x8 cm", "weight_kg": 0.5},
             "dietary_tags": {"vegan": True, "gluten_free": True, "organic": True},
             "tags": "organic,vegan,gluten-free,baking,value"},
            {"sku": "COCO-1KG",  "name": "1kg Bag",   "base_price": 39.99, "quantity": 30,
             "attributes": {"weight": "1kg", "package_type": "bag"},
             "specifications": {"dimensions": "25x20x12 cm", "weight_kg": 1.0},
             "dietary_tags": {"vegan": True, "gluten_free": True, "organic": True},
             "tags": "organic,vegan,gluten-free,baking,bulk"},
        ],
    },
    {
        "name": "Shea Butter Moisturizer",
        "slug": "shea-butter-moisturizer",
        "description": "Pure African shea butter for deep skin hydration. Natural and unrefined from Ghana and Burkina Faso.",
        "short_description": "Pure African shea butter for deep hydration",
        "category": "beauty",
        "product_metadata": {"origin": "Ghana/Burkina Faso", "skin_types": ["all", "dry", "sensitive"]},
        "variants": [
            {"sku": "SHEA-100ML", "name": "100ml Jar", "base_price": 9.99,  "quantity": 60,
             "attributes": {"volume": "100ml", "container": "jar"},
             "specifications": {"dimensions": "6x6x5 cm", "weight_kg": 0.12},
             "dietary_tags": {}, "tags": "natural,moisturizer,skincare,travel-size"},
            {"sku": "SHEA-250ML", "name": "250ml Jar", "base_price": 18.99, "quantity": 45,
             "attributes": {"volume": "250ml", "container": "jar"},
             "specifications": {"dimensions": "8x8x7 cm", "weight_kg": 0.28},
             "dietary_tags": {}, "tags": "natural,moisturizer,skincare"},
            {"sku": "SHEA-500ML", "name": "500ml Jar", "base_price": 32.99, "quantity": 25,
             "attributes": {"volume": "500ml", "container": "jar"},
             "specifications": {"dimensions": "10x10x9 cm", "weight_kg": 0.55},
             "dietary_tags": {}, "tags": "natural,moisturizer,skincare,family-size"},
        ],
    },
    {
        "name": "Handwoven Kente Cloth",
        "slug": "handwoven-kente-cloth",
        "description": "Authentic Ghanaian Kente cloth handwoven by skilled artisans. Traditional patterns with rich cultural significance.",
        "short_description": "Authentic handwoven Ghanaian Kente cloth",
        "category": "fashion",
        "product_metadata": {"origin": "Ghana", "craft": "handwoven", "material": "cotton/silk blend"},
        "variants": [
            {"sku": "KENTE-STOLE", "name": "Graduation Stole", "base_price": 45.99, "quantity": 20,
             "attributes": {"size": "stole", "length": "72 inches"},
             "specifications": {"dimensions": "180x15 cm", "weight_kg": 0.3},
             "dietary_tags": {}, "tags": "handwoven,traditional,graduation,gift"},
            {"sku": "KENTE-2YARD", "name": "2 Yards",           "base_price": 89.99, "quantity": 15,
             "attributes": {"size": "2 yards", "width": "46 inches"},
             "specifications": {"dimensions": "180x117 cm", "weight_kg": 0.8},
             "dietary_tags": {}, "tags": "handwoven,traditional,ceremonial"},
            {"sku": "KENTE-4YARD", "name": "4 Yards",           "base_price": 169.99, "quantity": 10,
             "attributes": {"size": "4 yards", "width": "46 inches"},
             "specifications": {"dimensions": "360x117 cm", "weight_kg": 1.5},
             "dietary_tags": {}, "tags": "handwoven,traditional,ceremonial,premium"},
        ],
    },
    {
        "name": "Baobab Superfood Powder",
        "slug": "baobab-superfood-powder",
        "description": "Nutrient-rich baobab fruit powder. High in vitamin C, fibre, and antioxidants. Sustainably harvested from African baobab trees.",
        "short_description": "Nutrient-rich African baobab superfood powder",
        "category": "food",
        "product_metadata": {"origin": "Zimbabwe/Malawi", "superfood": True},
        "variants": [
            {"sku": "BAOBAB-100G", "name": "100g Pouch", "base_price": 14.99, "quantity": 80,
             "attributes": {"weight": "100g", "package_type": "pouch"},
             "specifications": {"dimensions": "12x8x2 cm", "weight_kg": 0.1},
             "dietary_tags": {"vegan": True, "gluten_free": True, "raw": True},
             "tags": "superfood,vegan,gluten-free,immune-boost"},
            {"sku": "BAOBAB-250G", "name": "250g Pouch", "base_price": 29.99, "quantity": 50,
             "attributes": {"weight": "250g", "package_type": "pouch"},
             "specifications": {"dimensions": "18x12x4 cm", "weight_kg": 0.25},
             "dietary_tags": {"vegan": True, "gluten_free": True, "raw": True},
             "tags": "superfood,vegan,gluten-free,immune-boost,value"},
            {"sku": "BAOBAB-500G", "name": "500g Pouch", "base_price": 49.99, "quantity": 30,
             "attributes": {"weight": "500g", "package_type": "pouch"},
             "specifications": {"dimensions": "22x16x6 cm", "weight_kg": 0.5},
             "dietary_tags": {"vegan": True, "gluten_free": True, "raw": True},
             "tags": "superfood,vegan,gluten-free,immune-boost,bulk"},
        ],
    },
    {
        "name": "African Black Soap",
        "slug": "african-black-soap",
        "description": "Traditional African black soap made with plantain skins, cocoa pod powder, and palm kernel oil. Great for all skin types.",
        "short_description": "Traditional African black soap for all skin types",
        "category": "beauty",
        "product_metadata": {"origin": "Ghana/Nigeria", "skin_concerns": ["acne", "eczema", "dark spots"]},
        "variants": [
            {"sku": "BLACKSOAP-1BAR",  "name": "Single Bar", "base_price": 6.99,  "quantity": 100,
             "attributes": {"size": "single", "weight": "150g"},
             "specifications": {"dimensions": "8x5x3 cm", "weight_kg": 0.15},
             "dietary_tags": {}, "tags": "natural,skincare,acne,traditional"},
            {"sku": "BLACKSOAP-3PACK", "name": "3-Pack",     "base_price": 18.99, "quantity": 50,
             "attributes": {"size": "3-pack", "weight": "450g total"},
             "specifications": {"dimensions": "15x10x4 cm", "weight_kg": 0.45},
             "dietary_tags": {}, "tags": "natural,skincare,acne,traditional,value-pack"},
            {"sku": "BLACKSOAP-6PACK", "name": "6-Pack",     "base_price": 34.99, "quantity": 30,
             "attributes": {"size": "6-pack", "weight": "900g total"},
             "specifications": {"dimensions": "20x15x6 cm", "weight_kg": 0.9},
             "dietary_tags": {}, "tags": "natural,skincare,acne,traditional,bulk-save"},
        ],
    },
    {
        "name": "Moringa Leaf Powder",
        "slug": "moringa-leaf-powder",
        "description": "Pure moringa leaf powder from East Africa. Packed with vitamins, minerals, and amino acids. The ultimate superfood.",
        "short_description": "Pure East African moringa leaf powder",
        "category": "food",
        "product_metadata": {"origin": "Kenya/Tanzania", "superfood": True},
        "variants": [
            {"sku": "MORINGA-100G", "name": "100g Pouch", "base_price": 11.99, "quantity": 90,
             "attributes": {"weight": "100g", "package_type": "pouch"},
             "specifications": {"dimensions": "12x8x2 cm", "weight_kg": 0.1},
             "dietary_tags": {"vegan": True, "gluten_free": True},
             "tags": "superfood,vegan,gluten-free,moringa"},
            {"sku": "MORINGA-250G", "name": "250g Pouch", "base_price": 24.99, "quantity": 60,
             "attributes": {"weight": "250g", "package_type": "pouch"},
             "specifications": {"dimensions": "18x12x4 cm", "weight_kg": 0.25},
             "dietary_tags": {"vegan": True, "gluten_free": True},
             "tags": "superfood,vegan,gluten-free,moringa,value"},
        ],
    },
]


async def seed(force: bool = False):
    db_manager.initialize(settings.SQLALCHEMY_DATABASE_URI, False)
    from core.db import AsyncSessionDB
    async with AsyncSessionDB() as db:
        if force:
            print("--force/--drop provided: truncating seeded tables (CASCADE)")
            # Truncate product/catalog and commerce tables used by the seeder.
            # Use schema-qualified names to be explicit.
            await db.execute(text(
                "TRUNCATE TABLE catalog.stock_adjustments, catalog.inventory,"
                " catalog.product_images, catalog.product_variants, catalog.reviews,"
                " catalog.products CASCADE"
            ))
            await db.execute(text(
                "TRUNCATE TABLE commerce.shipping_methods, commerce.tax_rates CASCADE"
            ))
            await db.commit()
        now = datetime.now(timezone.utc)
        pm = PasswordManager()

        # ── Admin user ──────────────────────────────────────────────
        existing_admin = await db.scalar(select(User).filter_by(email="admin@banwee.com"))
        if existing_admin:
            admin = existing_admin
            print("Admin user already exists, using existing user")
        else:
            admin = User(
                id=uuid7(),
                email="admin@banwee.com",
                firstname="Admin",
                lastname="Banwee",
                hashed_password=pm.hash_password("AdminPass123!"),
                role="admin",
                account_status="active",
                verification_status="verified",
                phone_verified=False,
                language="en",
                failed_login_attempts=0,
            )
            db.add(admin)

        # ── Warehouse location ──────────────────────────────────────
        location = WarehouseLocation(
            id=uuid7(),
            name="Main Warehouse",
            address="Accra, Ghana",
            description="Primary fulfilment centre",
        )
        db.add(location)
        await db.flush()

        # ── Sample customer users ───────────────────────────────────
        customers = []
        customer_data = [
            {"email": "alice@example.com", "firstname": "Alice", "lastname": "Cooper"},
            {"email": "bob@example.com", "firstname": "Bob", "lastname": "Smith"},
            {"email": "carol@example.com", "firstname": "Carol", "lastname": "Jones"},
        ]
        for c in customer_data:
            existing = await db.scalar(select(User).filter_by(email=c["email"]))
            if existing:
                customers.append(existing)
                print(f"Customer {c['email']} already exists, skipping")
            else:
                user = User(
                    id=uuid7(),
                    email=c["email"],
                    firstname=c["firstname"],
                    lastname=c["lastname"],
                    hashed_password=pm.hash_password("Password123!"),
                    role="customer",
                    account_status="active",
                    verification_status="verified",
                    phone_verified=False,
                    language="en",
                    failed_login_attempts=0,
                )
                db.add(user)
                customers.append(user)
        await db.flush()

        # ── Products, variants, inventory ──────────────────────────
        total_variants = 0
        products_created = []
        for p_data in PRODUCTS:
            # check existing product by slug to make seeding idempotent
            existing_prod = await db.scalar(select(Product).filter_by(slug=p_data["slug"]))
            if existing_prod:
                product = existing_prod
                print(f"Product {p_data['slug']} already exists, using existing record")
            else:
                product = Product(
                    id=uuid7(),
                    name=p_data["name"],
                    slug=p_data["slug"],
                    description=p_data["description"],
                    short_description=p_data.get("short_description"),
                    category=p_data["category"],
                    product_status="active",
                    rating_average=0.0,
                    rating_count=0,
                    review_count=0,
                    is_featured=True,
                    is_bestseller=False,
                    published_at=now,
                    product_metadata=p_data.get("product_metadata"),
                )
                db.add(product)
                await db.flush()
            products_created.append(product)

            for idx, v in enumerate(p_data["variants"]):
                # check existing variant by SKU
                existing_variant = await db.scalar(select(ProductVariant).filter_by(sku=v["sku"]))
                if existing_variant:
                    variant = existing_variant
                    print(f"Variant {v['sku']} exists, skipping creation")
                else:
                    variant = ProductVariant(
                        id=uuid7(),
                        product_id=product.id,
                        sku=v["sku"],
                        name=v["name"],
                        base_price=v["base_price"],
                        sale_price=None,
                        availability_status="available",
                        is_active=True,
                        attributes=v.get("attributes", {}),
                        specifications=v.get("specifications", {}),
                        dietary_tags=v.get("dietary_tags", {}),
                        tags=v.get("tags"),
                        view_count=0,
                        purchase_count=0,
                    )
                    db.add(variant)
                    await db.flush()
                    total_variants += 1

                # inventory: create if not exists for this variant+location
                # inventory table has a uniqueness constraint on variant_id; check by variant_id
                existing_inventory = await db.scalar(select(Inventory).filter_by(variant_id=variant.id))
                if existing_inventory:
                    inventory = existing_inventory
                else:
                    inventory = Inventory(
                        id=uuid7(),
                        variant_id=variant.id,
                        location_id=location.id,
                        quantity_available=v["quantity"],
                        quantity=v["quantity"],
                        low_stock_threshold=10,
                        reorder_point=5,
                        inventory_status="active",
                        last_restocked_at=now,
                        version=0,
                    )
                    db.add(inventory)
                    await db.flush()
                    db.add(StockAdjustment(
                        id=uuid7(),
                        inventory_id=inventory.id,
                        quantity_change=v["quantity"],
                        reason="initial_stock",
                        notes=f"Seed: {v['sku']}",
                    ))

                # ensure at least two images exist for this variant
                existing_images = await db.execute(select(ProductImage).filter_by(variant_id=variant.id))
                imgs = existing_images.scalars().all()
                if len(imgs) >= 2:
                    pass
                else:
                    # Primary image
                    db.add(ProductImage(
                        id=uuid7(),
                        variant_id=variant.id,
                        url=f"https://cdn.banwee.com/products/{p_data['slug']}-{idx+1}.jpg",
                        alt_text=f"{p_data['name']} — {v['name']}",
                        is_primary=(idx == 0),
                        sort_order=idx,
                        format="jpg",
                    ))
                    # Secondary image
                    db.add(ProductImage(
                        id=uuid7(),
                        variant_id=variant.id,
                        url=f"https://cdn.banwee.com/products/{p_data['slug']}-{idx+1}-2.jpg",
                        alt_text=f"{p_data['name']} — {v['name']} (alt)",
                        is_primary=False,
                        sort_order=idx+1,
                        format="jpg",
                    ))

        # ── Shipping methods ────────────────────────────────────────
        shipping_methods = [
            ShippingMethod(id=uuid7(), name="Standard Shipping",  description="5-7 business days",  price=4.99,  estimated_days=6,  is_active=True, carrier="standard"),
            ShippingMethod(id=uuid7(), name="Express Shipping",   description="2-3 business days",  price=12.99, estimated_days=2,  is_active=True, carrier="express"),
            ShippingMethod(id=uuid7(), name="Overnight Shipping", description="Next business day",  price=24.99, estimated_days=1,  is_active=True, carrier="overnight"),
            ShippingMethod(id=uuid7(), name="Free Shipping",      description="7-10 business days", price=0.00,  estimated_days=8,  is_active=True, carrier="standard"),
        ]
        for sm in shipping_methods:
            db.add(sm)

        # ── Tax rates ───────────────────────────────────────────────
        tax_rates = [
            TaxRate(id=uuid7(), country_code="US", country_name="United States", province_code="CA", province_name="California", tax_rate=0.0725, tax_name="CA Sales Tax", is_active=True),
            TaxRate(id=uuid7(), country_code="US", country_name="United States", province_code="NY", province_name="New York",    tax_rate=0.08,   tax_name="NY Sales Tax", is_active=True),
            TaxRate(id=uuid7(), country_code="US", country_name="United States", province_code=None, province_name=None,          tax_rate=0.06,   tax_name="US Sales Tax", is_active=True),
            TaxRate(id=uuid7(), country_code="GB", country_name="United Kingdom", province_code=None, province_name=None,         tax_rate=0.20,   tax_name="VAT",          is_active=True),
            TaxRate(id=uuid7(), country_code="GH", country_name="Ghana",          province_code=None, province_name=None,         tax_rate=0.125,  tax_name="VAT",          is_active=True),
            TaxRate(id=uuid7(), country_code="CA", country_name="Canada",         province_code="ON", province_name="Ontario",    tax_rate=0.13,   tax_name="HST",          is_active=True),
            TaxRate(id=uuid7(), country_code="AU", country_name="Australia",      province_code=None, province_name=None,         tax_rate=0.10,   tax_name="GST",          is_active=True),
        ]
        for tr in tax_rates:
            db.add(tr)

        # ── Related products (by similarity) ───────────────────────
        # Compute related products using seeded data similarity:
        # same category (+3), matching tags (+2 each), matching dietary tags (+1 each), matching attribute keys (+1 each)
        def _features_from_seed(seed_entry):
            tag_set = set()
            dietary_set = set()
            attr_keys = set()
            for vv in seed_entry.get("variants", []):
                if vv.get("tags"):
                    tag_set.update([t.strip() for t in str(vv.get("tags", "")).split(",") if t.strip()])
                if vv.get("dietary_tags"):
                    dietary_set.update([k for k, val in vv.get("dietary_tags", {}).items() if val])
                if vv.get("attributes"):
                    attr_keys.update(vv.get("attributes", {}).keys())
            return tag_set, dietary_set, attr_keys

        # build feature list from PRODUCTS (seed data) in the same order as products_created
        seed_features = [_features_from_seed(p) for p in PRODUCTS[: len(products_created)]]

        for i, prod in enumerate(products_created):
            p_tags, p_diet, p_attrs = seed_features[i]
            scores = []
            for j, other in enumerate(products_created):
                if i == j:
                    continue
                o_tags, o_diet, o_attrs = seed_features[j]
                score = 0
                # category match
                if PRODUCTS[i].get("category") == PRODUCTS[j].get("category"):
                    score += 3
                # tag overlap
                score += 2 * len(p_tags & o_tags)
                # dietary overlap
                score += 1 * len(p_diet & o_diet)
                # attribute key overlap
                score += 1 * len(p_attrs & o_attrs)
                scores.append((score, other.id))

            # pick top 2 with positive score, stable sort
            scores.sort(key=lambda x: (-x[0], str(x[1])))
            related = [str(s[1]) for s in scores[:2] if s[0] > 0]
            meta = prod.product_metadata or {}
            meta["related_product_ids"] = related
            prod.product_metadata = meta
            db.add(prod)

        # ── Seed reviews for products ──────────────────────────────
        # Create 2 reviews per product from sample customers and update aggregates
        for i, prod in enumerate(products_created):
            # deterministic ratings for variety
            ratings = [5, 4] if i % 2 == 0 else [4, 3]
            for j, rating in enumerate(ratings):
                reviewer = customers[(i + j) % len(customers)] if customers else admin
                review = Review(
                    id=uuid7(),
                    product_id=prod.id,
                    user_id=reviewer.id,
                    rating=rating,
                    comment=f"Seed review ({rating} stars) for {prod.name}",
                    is_verified_purchase=True,
                    is_approved=True,
                )
                db.add(review)
                # update product aggregates
                prev_count = prod.rating_count or 0
                prev_avg = prod.rating_average or 0.0
                new_total = prev_avg * prev_count + rating
                new_count = prev_count + 1
                prod.rating_count = new_count
                prod.review_count = (prod.review_count or 0) + 1
                prod.rating_average = round(new_total / new_count, 2)
                db.add(prod)

        await db.commit()

        print(f"✓ Admin user:       admin@banwee.com / AdminPass123!")
        print(f"✓ Products:         {len(PRODUCTS)} products, {total_variants} variants")
        print(f"✓ Shipping methods: {len(shipping_methods)}")
        print(f"✓ Tax rates:        {len(tax_rates)} countries/regions")
        print("Seed complete.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed the Banwee database")
    parser.add_argument("--force", "--drop", dest="force", action="store_true",
                        help="Truncate seeded tables and reseed (useful for fresh test DBs)")
    args = parser.parse_args()

    asyncio.run(seed(force=args.force))
