"""Tests for services/catalog/review.py - ReviewService.

Covers the ownership checks on update/delete (a review can only be changed
by the user who wrote it), the one-review-per-user-per-product constraint,
and _update_product_rating/recalc_ratings - the aggregation logic that
keeps Product.rating_average/rating_count/review_count in sync.
"""

import pytest
from uuid import uuid4

from core.exceptions import APIException
from services.catalog.review import ReviewService
from services.accounts.auth import AuthService
from schemas.catalog.review import Create as ReviewCreate, Update as ReviewUpdate
from models.catalog.product import Product
from models.accounts.user import User, UserRole


async def make_product(db_session, **overrides) -> Product:
    fields = {
        "id": uuid4(),
        "name": "Test Product",
        "slug": f"test-product-{uuid4().hex[:8]}",
    }
    fields.update(overrides)
    product = Product(**fields)
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product


async def make_user(db_session, **overrides) -> User:
    auth = AuthService(db_session)
    fields = {
        "id": uuid4(),
        "email": f"review_test_{uuid4().hex[:8]}@example.com",
        "firstname": "Test",
        "lastname": "Reviewer",
        "hashed_password": auth.get_password_hash("Password123!"),
        "role": UserRole.CUSTOMER,
        "account_status": "active",
        "verification_status": "verified",
    }
    fields.update(overrides)
    user = User(**fields)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


class TestCreate:

    async def test_creates_a_review(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        result = await service.create(ReviewCreate(product_id=product.id, rating=5, comment="Great!"), user.id)
        assert result["rating"] == 5
        assert result["comment"] == "Great!"

    async def test_updates_product_rating_average_and_count(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        await service.create(ReviewCreate(product_id=product.id, rating=4), user.id)

        await db_session.refresh(product)
        assert float(product.rating_average) == pytest.approx(4.0)
        assert product.rating_count == 1
        assert product.review_count == 1

    async def test_unknown_product_is_rejected(self, db_session):
        user = await make_user(db_session)
        service = ReviewService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.create(ReviewCreate(product_id=uuid4(), rating=3), user.id)
        assert exc_info.value.status_code == 404

    async def test_duplicate_review_by_same_user_is_rejected(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        await service.create(ReviewCreate(product_id=product.id, rating=5), user.id)
        with pytest.raises(APIException) as exc_info:
            await service.create(ReviewCreate(product_id=product.id, rating=1), user.id)
        assert exc_info.value.status_code == 400


class TestGet:

    async def test_gets_by_id(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        created = await service.create(ReviewCreate(product_id=product.id, rating=3), user.id)
        found = await service.get(created["id"])
        assert str(found.id) == created["id"]

    async def test_unknown_id_returns_none(self, db_session):
        service = ReviewService(db_session)
        assert await service.get(uuid4()) is None


class TestList:

    async def test_lists_with_pagination_envelope(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        await service.create(ReviewCreate(product_id=product.id, rating=4), user.id)

        result = await service.list(product_id=product.id)
        assert result["total"] == 1
        assert result["page"] == 1
        assert len(result["data"]) == 1

    async def test_filters_by_rating_range(self, db_session):
        product = await make_product(db_session)
        service = ReviewService(db_session)
        for rating in (1, 3, 5):
            user = await make_user(db_session)
            await service.create(ReviewCreate(product_id=product.id, rating=rating), user.id)

        result = await service.list(product_id=product.id, min_rating=3, max_rating=5)
        assert result["total"] == 2

    async def test_sort_by_invalid_field_falls_back_to_default(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        await service.create(ReviewCreate(product_id=product.id, rating=4), user.id)

        result = await service.list(product_id=product.id, sort_by="not_a_real_field_desc")
        assert result["total"] == 1

    async def test_sort_by_rating_ascending(self, db_session):
        product = await make_product(db_session)
        service = ReviewService(db_session)
        for rating in (5, 1, 3):
            user = await make_user(db_session)
            await service.create(ReviewCreate(product_id=product.id, rating=rating), user.id)

        result = await service.list(product_id=product.id, sort_by="rating_asc")
        assert [r.rating for r in result["data"]] == [1, 3, 5]


class TestUpdate:

    async def test_owner_can_update(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        created = await service.create(ReviewCreate(product_id=product.id, rating=2), user.id)

        updated = await service.update(created["id"], ReviewUpdate(rating=5, comment="Actually great"), user.id)
        assert updated.rating == 5
        assert updated.comment == "Actually great"

    async def test_update_refreshes_product_rating(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        created = await service.create(ReviewCreate(product_id=product.id, rating=1), user.id)
        await service.update(created["id"], ReviewUpdate(rating=5), user.id)

        await db_session.refresh(product)
        assert float(product.rating_average) == pytest.approx(5.0)

    async def test_unknown_id_raises_404(self, db_session):
        user = await make_user(db_session)
        service = ReviewService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.update(uuid4(), ReviewUpdate(rating=3), user.id)
        assert exc_info.value.status_code == 404

    async def test_non_owner_cannot_update(self, db_session):
        product = await make_product(db_session)
        owner = await make_user(db_session)
        other = await make_user(db_session)
        service = ReviewService(db_session)
        created = await service.create(ReviewCreate(product_id=product.id, rating=4), owner.id)

        with pytest.raises(APIException) as exc_info:
            await service.update(created["id"], ReviewUpdate(rating=1), other.id)
        assert exc_info.value.status_code == 403


class TestDelete:

    async def test_owner_can_delete(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        created = await service.create(ReviewCreate(product_id=product.id, rating=3), user.id)

        await service.delete(created["id"], user.id)
        assert await service.get(created["id"]) is None

    async def test_delete_updates_product_rating_count(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        created = await service.create(ReviewCreate(product_id=product.id, rating=3), user.id)

        await service.delete(created["id"], user.id)
        await db_session.refresh(product)
        assert product.review_count == 0

    async def test_unknown_id_raises_404(self, db_session):
        user = await make_user(db_session)
        service = ReviewService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.delete(uuid4(), user.id)
        assert exc_info.value.status_code == 404

    async def test_non_owner_cannot_delete(self, db_session):
        product = await make_product(db_session)
        owner = await make_user(db_session)
        other = await make_user(db_session)
        service = ReviewService(db_session)
        created = await service.create(ReviewCreate(product_id=product.id, rating=4), owner.id)

        with pytest.raises(APIException) as exc_info:
            await service.delete(created["id"], other.id)
        assert exc_info.value.status_code == 403


class TestRecalcRatings:

    async def test_recalculates_average_across_approved_reviews(self, db_session):
        product = await make_product(db_session)
        service = ReviewService(db_session)
        for rating in (2, 4):
            user = await make_user(db_session)
            await service.create(ReviewCreate(product_id=product.id, rating=rating), user.id)

        updated_count = await service.recalc_ratings()
        assert updated_count >= 1
        await db_session.refresh(product)
        assert float(product.rating_average) == pytest.approx(3.0)
        assert product.rating_count == 2

    async def test_unapproved_reviews_are_excluded_from_the_join(self, db_session):
        """recalc_ratings() only touches products that still have >=1 approved
        review (its query inner-joins on is_approved=True) - a product whose
        only review just got unapproved is skipped entirely rather than reset
        to zero. That's existing behavior, documented here rather than
        silently relied on."""
        other_product = await make_product(db_session)
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        # Another approved review must exist so the query returns at least one
        # row and updated_count reflects only the untouched product being skipped.
        other_user = await make_user(db_session)
        await service.create(ReviewCreate(product_id=other_product.id, rating=5), other_user.id)

        created = await service.create(ReviewCreate(product_id=product.id, rating=1), user.id)
        review = await service.get(created["id"])
        review.is_approved = False
        await db_session.commit()

        await service.recalc_ratings()
        await db_session.refresh(product)
        assert product.rating_count == 1  # untouched, not reset to 0
