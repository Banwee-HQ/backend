"""Tests for schemas/catalog/review.py - rating range constraint."""

import pytest
from pydantic import ValidationError

from schemas.catalog.review import Base, Update


class TestBaseRatingConstraint:

    def test_rejects_rating_above_five(self):
        from uuid import uuid4
        with pytest.raises(ValidationError):
            Base(product_id=uuid4(), rating=6)

    def test_rejects_rating_below_one(self):
        from uuid import uuid4
        with pytest.raises(ValidationError):
            Base(product_id=uuid4(), rating=0)

    def test_accepts_valid_rating(self):
        from uuid import uuid4
        review = Base(product_id=uuid4(), rating=5)
        assert review.rating == 5


class TestUpdateOptionalProductId:

    def test_allows_omitting_product_id(self):
        update = Update(rating=4)
        assert update.product_id is None
