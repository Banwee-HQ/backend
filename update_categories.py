#!/usr/bin/env python3
"""
One-off script to update existing product categories in the DB
to use the new CATEGORIES slugs at random.
"""
import asyncio
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from core.config import settings
from core.db import db_manager

CATEGORIES = [
    {"name": "Grains, Cereals & Beans",    "slug": "grains-pulses"},
    {"name": "Fruits & Vegetables",         "slug": "fruits-vegetables"},
    {"name": "Meat, Poultry & Seafood",     "slug": "meat-seafood"},
    {"name": "Dairy, Eggs & Fats",          "slug": "dairy-fats"},
    {"name": "Spices, Herbs & Seasonings",  "slug": "spices-herbs"},
    {"name": "Pantry & Sweeteners",         "slug": "pantry-sweeteners"},
    {"name": "Nuts, Seeds & Snacks",        "slug": "nuts-seeds-snacks"},
    {"name": "Beverages, Tea & Coffee",     "slug": "beverages"},
    {"name": "Bakery & Prepared Foods",     "slug": "bakery"},
    {"name": "Fibers & Industrial Crops",   "slug": "fibers"},
]

SLUGS = [c["slug"] for c in CATEGORIES]


async def update():
    # Ensure async driver is used
    db_url = settings.DATABASE_URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    db_manager.initialize(db_url, env_is_local=True)

    async with db_manager.session_factory() as session:
        # Fetch all product ids
        result = await session.execute(text("SELECT id FROM catalog.products"))
        product_ids = [row[0] for row in result.fetchall()]

        if not product_ids:
            print("No products found.")
            return

        print(f"Updating {len(product_ids)} products...")

        for pid in product_ids:
            slug = random.choice(SLUGS)
            await session.execute(
                text("UPDATE catalog.products SET category = :cat WHERE id = :id"),
                {"cat": slug, "id": str(pid)},
            )
            print(f"  {pid} → {slug}")

        await session.commit()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(update())
