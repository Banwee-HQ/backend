"""Tests for models/catalog/review.py - Review.

No to_dict()/properties on this model - just column defaults worth pinning.
Defaults only apply on INSERT (not at Python construction time), so these
need a real round-trip through the database.
"""

from uuid import uuid4
from decimal import Decimal

from core.utils.uuid_utils import uuid7
from models.catalog.review import Review
from models.catalog.category import Category
from models.catalog.product import Product


class TestReviewDefaults:

    async def test_defaults_to_unverified_and_approved(self, db_session, test_user):
        category = Category(id=uuid7(), name="Cat", slug=f"cat-{uuid4().hex[:8]}")
        product = Product(id=uuid7(), name="Widget", slug=f"widget-{uuid4().hex[:8]}", category_id=category.id)
        review = Review(id=uuid7(), product_id=product.id, user_id=test_user.id, rating=5)
        db_session.add_all([category, product, review])
        await db_session.commit()
        await db_session.refresh(review)
        assert review.is_verified_purchase is False
        assert review.is_approved is True

    def test_stores_rating_and_comment(self):
        review = Review(id=uuid7(), product_id=uuid7(), user_id=uuid7(), rating=4, comment="Pretty good")
        assert review.rating == 4
        assert review.comment == "Pretty good"
