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


class TestUpdateCannotMoveReview:

    def test_product_id_is_not_part_of_an_update(self):
        update = Update(rating=4, product_id="00000000-0000-0000-0000-000000000000")
        assert "product_id" not in update.model_dump(exclude_unset=True)
