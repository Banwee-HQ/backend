"""Seed the dev database with sample categories and products so the storefront has something to show.

Usage (from backend/, dev only):
    python scripts/seed_dev.py          # create sample data (safe to re-run; existing items are skipped)
    python scripts/seed_dev.py --clear  # remove everything this script created
Products are created through ProductService, exactly as the admin "New product" form would.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env.dev")

from sqlalchemy import delete, event, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from models import *  # noqa: E402,F401,F403  (registers every mapper)
from models.catalog.category import Category  # noqa: E402
from models.catalog.product import Product  # noqa: E402
from schemas.catalog.product import Create as ProductCreate, VariantCreate  # noqa: E402
from services.catalog.products import ProductService  # noqa: E402

SEED_PREFIX = "sample-"  # every seeded product slug starts with this, which is how --clear finds them
SEED_MARK = "[sample data]"  # stored in seeded category descriptions for the same reason

# Slugs match the storefront's category tile images (frontend/src/data/categories.ts).
CATEGORIES = [
    ("grains-pulses", "Grains & Pulses", "https://as2.ftcdn.net/v2/jpg/10/35/29/29/1000_F_1035292924_5Un8kLGdN4k0DqgWVMI3JEm3Y7rpxSkF.jpg"),
    ("fruits-vegetables", "Fruits & Vegetables", "https://as1.ftcdn.net/v2/jpg/01/89/79/16/1000_F_189791663_HfB3CYN2oi7E2uKG1cY5HRRMFfiVJ3cR.jpg"),
    ("meat-seafood", "Meat & Seafood", "https://as2.ftcdn.net/v2/jpg/19/28/43/69/1000_F_1928436985_AJtwrZXKAbIvNmJXYlNjNgGQ4FBpsyX6.jpg"),
    ("dairy-fats", "Dairy & Fats", "https://as1.ftcdn.net/v2/jpg/19/44/23/90/1000_F_1944239098_SHLzOGrkPOn0OwoyCgzZFHXd6Ru3TpUu.jpg"),
    ("spices-herbs", "Spices & Herbs", "https://as1.ftcdn.net/v2/jpg/18/01/52/56/1000_F_1801525699_XcC9CxVAsOAeq1ANnXMZHI2IUNvHxytG.jpg"),
    ("pantry-sweeteners", "Pantry & Sweeteners", "https://as1.ftcdn.net/v2/jpg/19/41/36/84/1000_F_1941368437_2LLv91y4C1WjFT8MidWoZZGGbJCGPNQ1.jpg"),
    ("nuts-seeds-snacks", "Nuts, Seeds & Snacks", "https://as1.ftcdn.net/v2/jpg/19/40/12/60/1000_F_1940126016_2a19qvi9oIRGwokZxWDzRiK9P0Qgoa1R.jpg"),
    ("beverages", "Beverages", "https://as2.ftcdn.net/v2/jpg/18/00/81/35/1000_F_1800813561_5j5FkAO5vGiavGBIVxvGnQDBUbgkLQbk.jpg"),
    ("bakery", "Bakery", "https://as2.ftcdn.net/v2/jpg/19/13/97/67/1000_F_1913976756_KBvahysjlqAvNSgH5Wa6sL7HoBsansLK.jpg"),
    ("fibers", "Fibers", "https://as1.ftcdn.net/v2/jpg/19/22/40/42/1000_F_1922404257_6fmLscip64EtF6K9zbckxulHwg9qKHpT.jpg"),
]

# (category slug, name, description, origin, featured, [(variant name, base price, sale price, stock), ...])
PRODUCTS = [
    ("grains-pulses", "Ofada Rice", "Aromatic, unpolished short-grain rice grown in Ogun State.", "Nigeria", True,
     [("1 kg bag", 6.50, 5.50, 120), ("5 kg bag", 28.00, 28.00, 40)]),
    ("grains-pulses", "Honey Beans (Oloyin)", "Naturally sweet brown beans, ideal for ewa agoyin.", "Nigeria", False,
     [("1 kg bag", 5.20, 5.20, 90)]),
    ("fruits-vegetables", "Fresh Plantain", "Firm green plantain, perfect for frying or boiling.", "Ghana", True,
     [("Bunch of 5", 7.00, 6.00, 60)]),
    ("fruits-vegetables", "Scotch Bonnet Peppers", "Hot, fruity peppers for stews and pepper soup.", "Nigeria", False,
     [("250 g", 3.80, 3.80, 75)]),
    ("meat-seafood", "Smoked Catfish", "Wood-smoked catfish for soups and stews.", "Nigeria", False,
     [("2 pieces", 12.00, 10.50, 30)]),
    ("dairy-fats", "Red Palm Oil", "Unrefined red palm oil pressed from fresh palm fruit.", "Nigeria", True,
     [("1 litre", 8.50, 8.50, 50), ("5 litres", 38.00, 34.00, 15)]),
    ("spices-herbs", "Suya Spice (Yaji)", "Peanut-based spice blend for grilled meats.", "Nigeria", True,
     [("100 g jar", 4.50, 3.90, 100)]),
    ("spices-herbs", "Dried Uziza Leaves", "Peppery dried leaves for soups.", "Nigeria", False,
     [("50 g", 3.20, 3.20, 45)]),
    ("pantry-sweeteners", "Raw Forest Honey", "Unfiltered honey from the Mambilla Plateau.", "Nigeria", False,
     [("500 g jar", 11.00, 9.50, 40)]),
    ("nuts-seeds-snacks", "Roasted Groundnuts", "Crunchy roasted peanuts, lightly salted.", "Nigeria", False,
     [("500 g", 4.00, 4.00, 110)]),
    ("nuts-seeds-snacks", "Tiger Nuts", "Chewy, naturally sweet tiger nuts for snacking or kunu.", "Ghana", True,
     [("500 g", 6.80, 5.90, 70)]),
    ("beverages", "Zobo Hibiscus Leaves", "Dried roselle calyces for zobo drink.", "Nigeria", False,
     [("200 g", 3.50, 3.50, 85)]),
    ("bakery", "Chin Chin", "Crunchy fried pastry snack with a hint of nutmeg.", "Nigeria", False,
     [("400 g tub", 5.00, 4.50, 65)]),
    ("fibers", "Raffia Fiber Bundle", "Natural raffia palm fiber for weaving and crafts.", "Nigeria", False,
     [("1 kg bundle", 14.00, 14.00, 20)]),
]


def _require_dev() -> str:
    if os.getenv("ENVIRONMENT", "dev").lower() not in ("dev", "development", "local", "test"):
        sys.exit("Refusing to seed: ENVIRONMENT is not dev.")
    url = os.environ["DATABASE_URL"]
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


async def seed(db: AsyncSession) -> None:
    images = {slug: image for slug, _, image in CATEGORIES}
    categories = {}
    for order, (slug, name, _) in enumerate(CATEGORIES):
        category = (await db.execute(select(Category).where(Category.slug == slug))).scalar_one_or_none()
        if not category:
            category = Category(name=name, slug=slug, description=SEED_MARK, is_active=True, sort_order=order)
            db.add(category)
            await db.flush()
        categories[slug] = category
    await db.commit()

    service = ProductService(db)
    created = 0
    for cat_slug, name, description, origin, featured, variants in PRODUCTS:
        slug = SEED_PREFIX + name.lower().replace(" ", "-").replace("(", "").replace(")", "")
        if (await db.execute(select(Product.id).where(Product.slug == slug))).scalar_one_or_none():
            continue
        await service.create(ProductCreate(
            name=name, slug=slug, description=description, short_description=description,
            category_id=categories[cat_slug].id, origin=origin, is_featured=featured, sale_price=variants[0][2],
            variants=[
                VariantCreate(name=v_name, base_price=base, sale_price=sale, stock=stock, image_urls=[images[cat_slug]])
                for v_name, base, sale, stock in variants
            ],
        ), created_by=uuid4())
        created += 1
    print(f"Seeded {len(categories)} categories and {created} new products ({len(PRODUCTS) - created} already present).")


async def clear(db: AsyncSession) -> None:
    ids = (await db.execute(select(Product.id).where(Product.slug.startswith(SEED_PREFIX)))).scalars().all()
    service = ProductService(db)
    for product_id in ids:
        await service.delete(product_id, user_id=uuid4(), is_admin=True)
    removed = (await db.execute(delete(Category).where(Category.description == SEED_MARK))).rowcount
    await db.commit()
    print(f"Removed {len(ids)} sample products and {removed} sample categories.")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--clear", action="store_true", help="remove the sample data instead of creating it")
    args = parser.parse_args()

    engine = create_async_engine(_require_dev())

    @event.listens_for(engine.sync_engine, "connect")
    def _search_path(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("SET search_path TO accounts, catalog, commerce, admin, system, public")
        cursor.close()

    async with AsyncSession(engine, expire_on_commit=False) as db:
        await (clear(db) if args.clear else seed(db))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
